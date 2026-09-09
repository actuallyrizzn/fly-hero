"""Eyes produce FeatureFrames. They must not emit hit clocks."""

from __future__ import annotations

from typing import Protocol

from flyhero.types import DEFAULT_DEPTH, FeatureFrame


class Eye(Protocol):
    def see(self, t_seconds: float) -> FeatureFrame:
        """Picture of the highway at ``t_seconds``. No oracle timestamps."""


class NullEye:
    """Empty highway. Phase 0 stub so the player loop can run in tests."""

    def __init__(self, depth: int = DEFAULT_DEPTH) -> None:
        if depth < 1:
            raise ValueError("depth must be at least 1")
        self.depth = depth

    def see(self, t_seconds: float) -> FeatureFrame:
        return FeatureFrame.empty(depth=self.depth, t_seconds=t_seconds)
