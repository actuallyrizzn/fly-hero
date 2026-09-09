"""Wall-clock play. ChartEye is the fallback if pixels are not ready."""

from __future__ import annotations

import time

from flyhero.chart import Chart
from flyhero.chart_eye import ChartEye
from flyhero.eye import Eye
from flyhero.hands import Hands
from flyhero.player import Player
from flyhero.readout import Readout
from flyhero.reservoir import NullReservoir, Reservoir
from flyhero.train import NearBinReadout
from flyhero.types import DEFAULT_DEPTH, LANE_COUNT, Action


def play_live(
    chart: Chart,
    hands: Hands,
    *,
    eye: Eye | None = None,
    reservoir: Reservoir | None = None,
    readout: Readout | None = None,
    look_ahead: float = 1.5,
    depth: int = DEFAULT_DEPTH,
    step: float = 0.02,
    countdown: float = 0.0,
    clock=None,
    sleeper=None,
) -> list[Action]:
    """Tick the player from t=0 using a wall clock.

    ``countdown`` is empty highway time (Clone Hero 3-2-1) before chart t=0.
    ``clock`` / ``sleeper`` are injectables so CI does not sleep for real.
    """
    if step <= 0:
        raise ValueError("step must be positive")
    if countdown < 0:
        raise ValueError("countdown cannot be negative")
    now = clock or time.monotonic
    pause = sleeper or time.sleep
    seen = eye or ChartEye(chart, look_ahead=look_ahead, depth=depth)
    res = reservoir or NullReservoir(size=LANE_COUNT * depth)
    out = readout or NearBinReadout()
    player = Player(eye=seen, reservoir=res, readout=out, hands=hands)
    player.reset()
    actions: list[Action] = []
    t0 = now()
    end = countdown + chart.duration_seconds + look_ahead
    while True:
        elapsed = now() - t0
        if elapsed > end + 1e-9:
            break
        chart_t = elapsed - countdown
        if hasattr(hands, "set_time"):
            hands.set_time(max(chart_t, 0.0))
        if chart_t < 0:
            action = Action.idle()
            hands.apply(action)
        else:
            action = player.tick(chart_t)
        actions.append(action)
        target = t0 + (len(actions) * step)
        delay = target - now()
        if delay > 0:
            pause(delay)
    return actions
