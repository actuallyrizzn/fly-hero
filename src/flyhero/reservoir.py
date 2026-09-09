"""Frozen recurrent graph. ``W`` does not train."""

from __future__ import annotations

from typing import Protocol, Sequence


class Reservoir(Protocol):
    @property
    def size(self) -> int: ...

    def reset(self) -> None: ...

    def step(self, drive: Sequence[float]) -> tuple[float, ...]:
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
