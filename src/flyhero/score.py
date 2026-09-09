"""Grade a key log against chart notes. Chart times score; they are not player input."""

from __future__ import annotations

from dataclasses import dataclass

from flyhero.chart import Chart
from flyhero.guitar import GuitarMap, KeyEvent
from flyhero.types import LANE_COUNT

DEFAULT_WINDOW = 0.3
ACCEPT_FLOOR = 1.0


@dataclass(frozen=True)
class ScoreReport:
    notes: int
    hits: int
    misses: int
    accuracy: float
    window: float

    def accepted(self, floor: float = ACCEPT_FLOOR) -> bool:
        if not 0.0 <= floor <= 1.0:
            raise ValueError("floor must be in [0, 1]")
        return self.accuracy + 1e-12 >= floor


def _held_intervals(events: list[KeyEvent], key: str) -> list[tuple[float, float]]:
    intervals: list[tuple[float, float]] = []
    start: float | None = None
    for event in events:
        if event.key != key:
            continue
        if event.down:
            if start is None:
                start = event.t_seconds
        elif start is not None:
            intervals.append((start, event.t_seconds))
            start = None
    if start is not None:
        end = events[-1].t_seconds if events else start
        intervals.append((start, max(end, start)))
    return intervals


def _overlaps(intervals: list[tuple[float, float]], lo: float, hi: float) -> bool:
    for start, end in intervals:
        if start <= hi and end >= lo:
            return True
    return False


def score_events(
    chart: Chart,
    events: list[KeyEvent],
    *,
    mapping: GuitarMap | None = None,
    window: float = DEFAULT_WINDOW,
) -> ScoreReport:
    """A note hits when its fret and the strum are held inside the time window."""
    if window <= 0:
        raise ValueError("window must be positive")
    if not chart.notes:
        raise ValueError("chart has no notes to score")
    mapping = mapping or GuitarMap()
    fret_keys = [mapping.name(code) for code in mapping.fret_codes]
    strum_key = mapping.name(mapping.strum_code)
    strum_holds = _held_intervals(events, strum_key)
    lane_holds = [_held_intervals(events, fret_keys[lane]) for lane in range(LANE_COUNT)]
    hits = 0
    for note in chart.notes:
        lo = note.t_seconds - window
        hi = note.t_seconds + window
        if _overlaps(lane_holds[note.lane], lo, hi) and _overlaps(strum_holds, lo, hi):
            hits += 1
    total = len(chart.notes)
    return ScoreReport(
        notes=total,
        hits=hits,
        misses=total - hits,
        accuracy=hits / total,
        window=window,
    )


def score_log(chart: Chart, log, *, window: float = DEFAULT_WINDOW) -> ScoreReport:
    mapping = getattr(log, "mapping", None)
    return score_events(chart, list(log.events), mapping=mapping, window=window)
