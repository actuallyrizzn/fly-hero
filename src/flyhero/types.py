"""Shared value types. Five frets, one strum — Guitar Hero shape."""

from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum

LANE_COUNT = 5
DEFAULT_DEPTH = 8


class Lane(IntEnum):
    GREEN = 0
    RED = 1
    YELLOW = 2
    BLUE = 3
    ORANGE = 4


@dataclass(frozen=True)
class FeatureFrame:
    """What an eye is allowed to tell the player.

    ``cells[lane][near → far]`` is occupancy in [0, 1].
    This is a *picture* of the highway, not a list of hit timestamps.
    """

    cells: tuple[tuple[float, ...], ...]
    t_seconds: float

    def __post_init__(self) -> None:
        if len(self.cells) != LANE_COUNT:
            raise ValueError(f"need {LANE_COUNT} lanes, got {len(self.cells)}")
        depth = len(self.cells[0])
        if depth < 1:
            raise ValueError("depth must be at least 1")
        if any(len(row) != depth for row in self.cells):
            raise ValueError("all lanes must share the same depth")
        for row in self.cells:
            for value in row:
                if not 0.0 <= value <= 1.0:
                    raise ValueError(f"cell out of range: {value}")

    @property
    def depth(self) -> int:
        return len(self.cells[0])

    def as_vector(self) -> tuple[float, ...]:
        return tuple(v for row in self.cells for v in row)

    @classmethod
    def empty(cls, depth: int = DEFAULT_DEPTH, t_seconds: float = 0.0) -> FeatureFrame:
        blank = tuple(tuple(0.0 for _ in range(depth)) for _ in range(LANE_COUNT))
        return cls(cells=blank, t_seconds=t_seconds)

    @classmethod
    def from_rows(
        cls,
        rows: list[list[float]] | tuple[tuple[float, ...], ...],
        t_seconds: float = 0.0,
    ) -> FeatureFrame:
        cells = tuple(tuple(float(v) for v in row) for row in rows)
        return cls(cells=cells, t_seconds=t_seconds)


@dataclass(frozen=True)
class Action:
    """Fret holds plus whether to strum this tick."""

    frets: tuple[bool, bool, bool, bool, bool]
    strum: bool

    def __post_init__(self) -> None:
        if len(self.frets) != LANE_COUNT:
            raise ValueError(f"need {LANE_COUNT} frets, got {len(self.frets)}")

    @classmethod
    def idle(cls) -> Action:
        return cls(frets=(False, False, False, False, False), strum=False)

    @classmethod
    def from_frets(cls, frets: list[bool] | tuple[bool, ...], strum: bool) -> Action:
        return cls(frets=tuple(bool(f) for f in frets), strum=bool(strum))
