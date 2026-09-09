"""Turn timed notes into a highway *picture* (lanes × depth).

Near is bin 0. Far is the last bin. The player sees occupancies, not clocks.
"""

from __future__ import annotations

from flyhero.chart import Chart
from flyhero.types import DEFAULT_DEPTH, LANE_COUNT, FeatureFrame


def encode_highway(
    chart: Chart,
    t_seconds: float,
    *,
    look_ahead: float = 1.5,
    depth: int = DEFAULT_DEPTH,
) -> FeatureFrame:
    if look_ahead <= 0:
        raise ValueError("look_ahead must be positive")
    if depth < 1:
        raise ValueError("depth must be at least 1")
    rows = [[0.0] * depth for _ in range(LANE_COUNT)]
    for note in chart.notes:
        visible_from = note.t_seconds - look_ahead
        visible_until = note.t_seconds + note.sustain_seconds
        if t_seconds < visible_from or t_seconds > visible_until:
            continue
        if t_seconds >= note.t_seconds:
            # On or past the strike line: occupy the near bin while a hold lasts.
            rows[note.lane][0] = 1.0
            continue
        dt = note.t_seconds - t_seconds
        frac = dt / look_ahead
        index = min(depth - 1, max(0, int(frac * depth)))
        rows[note.lane][index] = 1.0
    return FeatureFrame.from_rows(rows, t_seconds=t_seconds)


def render_ascii(frame: FeatureFrame) -> str:
    """One character per cell. ``#`` occupied, ``.`` empty. Near is left."""
    names = "GRYBO"
    lines = []
    for i, row in enumerate(frame.cells):
        cells = "".join("#" if value >= 0.5 else "." for value in row)
        lines.append(f"{names[i]}|{cells}|")
    return "\n".join(lines)
