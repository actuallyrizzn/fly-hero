"""Frozen recurrent graph. ``W`` does not train."""

from __future__ import annotations

from typing import Protocol, Sequence

import numpy as np

from flyhero.connectome import Connectome, load_connectome, scramble, spectral_radius


class Reservoir(Protocol):
    @property
    def size(self) -> int: ...

    def reset(self) -> None: ...

    def step(self, drive: Sequence[float]) -> Sequence[float]:
        """Advance leaky state. Returns the new state vector."""


class NullReservoir:
    """Pass-through pad/truncate. Not a fly — a test double."""

    def __init__(self, size: int) -> None:
        if size < 1:
            raise ValueError("size must be at least 1")
        self._size = size
        self._state = tuple(0.0 for _ in range(size))

    @property
    def size(self) -> int:
        return self._size

    @property
    def state(self) -> tuple[float, ...]:
        return self._state

    def reset(self) -> None:
        self._state = tuple(0.0 for _ in range(self._size))

    def step(self, drive: Sequence[float]) -> tuple[float, ...]:
        values = [float(v) for v in drive]
        if len(values) < self._size:
            values.extend(0.0 for _ in range(self._size - len(values)))
        elif len(values) > self._size:
            values = values[: self._size]
        self._state = tuple(values)
        return self._state


class EchoReservoir:
    """Leaky tanh echo state over a fixed weight matrix.

    ``x ← (1−α)·x + α·tanh(W_in·u + W·x)``. ``W`` comes from a connectome (or a
    scrambled / random control) and is scaled once to a target spectral radius.
    ``W_in`` is a seeded random projection onto the chosen input neurons.
    Nothing here has a gradient.
    """

    def __init__(
        self,
        weights: np.ndarray,
        *,
        inputs: int,
        input_neurons: Sequence[int] | None = None,
        radius: float = 0.9,
        leak: float = 0.5,
        input_scale: float = 1.0,
        seed: int = 0,
    ) -> None:
        if weights.ndim != 2 or weights.shape[0] != weights.shape[1]:
            raise ValueError("weights must be square")
        if inputs < 1:
            raise ValueError("inputs must be at least 1")
        if not 0.0 < leak <= 1.0:
            raise ValueError("leak must be in (0, 1]")
        if radius <= 0:
            raise ValueError("radius must be positive")
        n = int(weights.shape[0])
        current = spectral_radius(weights, seed=seed)
        scale = radius / current if current > 0 else 1.0
        self.weights = (weights.astype(np.float32) * np.float32(scale)).astype(np.float32)
        self.leak = float(leak)
        self.inputs = int(inputs)
        rng = np.random.default_rng(seed)
        targets = (
            np.arange(n, dtype=np.int64)
            if input_neurons is None
            else np.asarray(list(input_neurons), dtype=np.int64)
        )
        if targets.size == 0:
            raise ValueError("need at least one input neuron")
        if targets.min() < 0 or targets.max() >= n:
            raise ValueError("input neuron index out of range")
        w_in = np.zeros((n, inputs), dtype=np.float32)
        w_in[targets] = rng.standard_normal((targets.size, inputs)).astype(np.float32) * np.float32(
            input_scale
        )
        self.w_in = w_in
        self.input_neurons = targets
        self._state = np.zeros(n, dtype=np.float32)

    @property
    def size(self) -> int:
        return int(self.weights.shape[0])

    @property
    def state(self) -> np.ndarray:
        """Current leaky activity vector (read-only view)."""
        return self._state

    def reset(self) -> None:
        self._state = np.zeros(self.size, dtype=np.float32)

    def step(self, drive: Sequence[float]) -> np.ndarray:
        u = np.asarray(drive, dtype=np.float32).reshape(-1)
        if u.size < self.inputs:
            u = np.concatenate([u, np.zeros(self.inputs - u.size, dtype=np.float32)])
        elif u.size > self.inputs:
            u = u[: self.inputs]
        pre = self.w_in @ u + self.weights.T @ self._state
        self._state = (1.0 - self.leak) * self._state + self.leak * np.tanh(pre)
        return self._state

    @classmethod
    def random(cls, size: int, *, inputs: int, density: float = 0.02, seed: int = 0, **kw) -> EchoReservoir:
        """Control: random sparse graph of the same size."""
        if size < 1:
            raise ValueError("size must be at least 1")
        if not 0.0 < density <= 1.0:
            raise ValueError("density must be in (0, 1]")
        rng = np.random.default_rng(seed)
        mask = rng.random((size, size)) < density
        weights = np.where(mask, rng.standard_normal((size, size)), 0.0).astype(np.float32)
        return cls(weights, inputs=inputs, seed=seed, **kw)

    @classmethod
    def from_connectome(
        cls,
        connectome: Connectome | None = None,
        *,
        inputs: int,
        drive: str | None = "sensory",
        scrambled: bool = False,
        seed: int = 0,
        **kw,
    ) -> EchoReservoir:
        """The fly. ``drive`` picks which cell type receives the highway picture."""
        graph = connectome or load_connectome()
        weights = scramble(graph.weights, seed=seed) if scrambled else graph.weights
        neurons = None
        if drive is not None:
            neurons = graph.neurons_of_type(drive)
            if neurons.size == 0:
                raise ValueError(f"connectome has no neurons of type {drive!r}")
        return cls(weights, inputs=inputs, input_neurons=neurons, seed=seed, **kw)
