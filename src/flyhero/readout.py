"""The only learned piece, later. Phase 0 is a silent stub."""

from __future__ import annotations

from typing import Protocol, Sequence

from flyhero.types import LANE_COUNT, Action


class Readout(Protocol):
    def act(self, state: Sequence[float]) -> Action: ...


class NullReadout:
    """Always idle. Proves the player can call a readout."""

    def act(self, state: Sequence[float]) -> Action:
        if not state:
            raise ValueError("readout needs a non-empty state")
        return Action.idle()


class ThresholdReadout:
    """Deterministic stand-in: fret n on if state[n] exceeds threshold.

    Used in harness tests so the loop is not a no-op. Not the trained fly.
    """

    def __init__(self, threshold: float = 0.5) -> None:
        if not 0.0 <= threshold <= 1.0:
            raise ValueError("threshold must be in [0, 1]")
        self.threshold = threshold

    def act(self, state: Sequence[float]) -> Action:
        if len(state) < LANE_COUNT:
            raise ValueError(f"need at least {LANE_COUNT} state units")
        frets = tuple(float(state[i]) >= self.threshold for i in range(LANE_COUNT))
        strum = any(frets)
        return Action.from_frets(frets, strum)
