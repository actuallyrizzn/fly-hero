"""Play a chart into hands. RecordingHands is the CI guitar; uinput is live."""

from __future__ import annotations

from flyhero.chart import Chart
from flyhero.chart_eye import ChartEye
from flyhero.eye import Eye
from flyhero.hands import Hands
from flyhero.player import Player
from flyhero.readout import Readout
from flyhero.reservoir import NullReservoir, Reservoir
from flyhero.train import NearBinReadout
from flyhero.types import LANE_COUNT, Action
from flyhero.uinput_hands import RecordingHands


def record_chart(
    chart: Chart,
    *,
    step: float = 0.25,
    look_ahead: float = 1.0,
    depth: int = 4,
    eye: Eye | None = None,
    reservoir: Reservoir | None = None,
    readout: Readout | None = None,
    hands: Hands | None = None,
) -> RecordingHands:
    """Run the player and return a key log a scorer can read."""
    if step <= 0:
        raise ValueError("step must be positive")
    seen = eye or ChartEye(chart, look_ahead=look_ahead, depth=depth)
    res = reservoir or NullReservoir(size=LANE_COUNT * depth)
    out = readout or NearBinReadout()
    log = hands if isinstance(hands, RecordingHands) else RecordingHands()
    if hands is None:
        hands = log
    player = Player(eye=seen, reservoir=res, readout=out, hands=hands)
    t = 0.0
    end = chart.duration_seconds + look_ahead
    actions: list[Action] = []
    while t <= end + 1e-9:
        if hasattr(hands, "set_time"):
            hands.set_time(t)
        actions.append(player.tick(t))
        t += step
    log.song_actions = actions
    return log
