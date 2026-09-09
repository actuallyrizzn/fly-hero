"""Virtual guitar mapping. Clone Hero defaults: frets 1–5, strum Down.

Bind Clone Hero's keyboard guitar to the same keys before a live run.
"""

from __future__ import annotations

from dataclasses import dataclass

from flyhero.types import LANE_COUNT, Action

# Linux input-event-codes.h — so CI does not need evdev installed.
EV_SYN = 0
EV_KEY = 1
SYN_REPORT = 0
KEY_1 = 2
KEY_2 = 3
KEY_3 = 4
KEY_4 = 5
KEY_5 = 6
KEY_UP = 103
KEY_DOWN = 108

DEFAULT_FRET_CODES: tuple[int, ...] = (KEY_1, KEY_2, KEY_3, KEY_4, KEY_5)
DEFAULT_STRUM_CODE = KEY_DOWN

CODE_NAME = {
    KEY_1: "1",
    KEY_2: "2",
    KEY_3: "3",
    KEY_4: "4",
    KEY_5: "5",
    KEY_UP: "up",
    KEY_DOWN: "down",
}


@dataclass(frozen=True)
class GuitarMap:
    fret_codes: tuple[int, ...] = DEFAULT_FRET_CODES
    strum_code: int = DEFAULT_STRUM_CODE

    def __post_init__(self) -> None:
        if len(self.fret_codes) != LANE_COUNT:
            raise ValueError(f"need {LANE_COUNT} fret codes")

    def name(self, code: int) -> str:
        return CODE_NAME.get(code, str(code))


@dataclass(frozen=True)
class KeyEvent:
    """One press or release. Used as the visual / scorer log."""

    t_seconds: float
    key: str
    down: bool

    def render(self) -> str:
        edge = "down" if self.down else "up"
        return f"{self.t_seconds:.2f} {self.key} {edge}"


def diff_action(previous: Action, current: Action, mapping: GuitarMap | None = None) -> list[tuple[int, bool]]:
    """Return (keycode, down) edges to go from previous to current."""
    mapping = mapping or GuitarMap()
    edges: list[tuple[int, bool]] = []
    for i, code in enumerate(mapping.fret_codes):
        if previous.frets[i] != current.frets[i]:
            edges.append((code, current.frets[i]))
    if previous.strum != current.strum:
        edges.append((mapping.strum_code, current.strum))
    return edges
