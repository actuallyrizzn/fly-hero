"""Supervised readout on highway pictures. Labels come from the near bin.

The player still only *sees* the frame. Labels are for training, not inference.
"""

from __future__ import annotations

from dataclasses import dataclass

from flyhero.chart import Chart
from flyhero.chart_eye import ChartEye
from flyhero.hands import NullHands
from flyhero.player import Player
from flyhero.reservoir import NullReservoir, Reservoir
from flyhero.types import LANE_COUNT, Action, FeatureFrame


@dataclass(frozen=True)
class Sample:
    frame: FeatureFrame
    action: Action


def label_from_frame(frame: FeatureFrame) -> Action:
    """Hold frets that occupy the strike-line bin. Strum if any."""
    frets = tuple(row[0] >= 0.5 for row in frame.cells)
    return Action.from_frets(frets, any(frets))


def collect_samples(
    chart: Chart,
    *,
    step: float = 0.05,
    look_ahead: float = 1.5,
    depth: int = 8,
) -> list[Sample]:
    if step <= 0:
        raise ValueError("step must be positive")
    eye = ChartEye(chart, look_ahead=look_ahead, depth=depth)
    end = chart.duration_seconds + look_ahead
    samples: list[Sample] = []
    t = 0.0
    while t <= end + 1e-9:
        frame = eye.see(t)
        samples.append(Sample(frame=frame, action=label_from_frame(frame)))
        t += step
    return samples


class NearBinReadout:
    """Deterministic POC readout: copy the strike-line bin.

    This is the features-only ceiling. A later fly readout has to beat or match it.
    """

    def act(self, state: list[float] | tuple[float, ...]) -> Action:
        # When driven by NullReservoir(size=lane*depth) the state *is* the frame.
        if len(state) < LANE_COUNT:
            raise ValueError("state too short for near-bin readout")
        depth = len(state) // LANE_COUNT
        if depth < 1 or len(state) != LANE_COUNT * depth:
            raise ValueError("state is not a full highway vector")
        frets = []
        for lane in range(LANE_COUNT):
            frets.append(float(state[lane * depth]) >= 0.5)
        return Action.from_frets(frets, any(frets))


def evaluate(
    chart: Chart,
    reservoir: Reservoir | None = None,
    *,
    step: float = 0.05,
    look_ahead: float = 1.5,
    depth: int = 8,
) -> dict[str, float]:
    """Accuracy of NearBinReadout vs labels on this chart."""
    samples = collect_samples(chart, step=step, look_ahead=look_ahead, depth=depth)
    res = reservoir or NullReservoir(size=LANE_COUNT * depth)
    res.reset()
    readout = NearBinReadout()
    correct = 0
    for sample in samples:
        state = res.step(sample.frame.as_vector())
        pred = readout.act(state)
        if pred == sample.action:
            correct += 1
    total = len(samples)
    return {"correct": float(correct), "total": float(total), "accuracy": correct / total}


def play_chart(
    chart: Chart,
    *,
    step: float = 0.05,
    look_ahead: float = 1.5,
    depth: int = 8,
) -> list[Action]:
    eye = ChartEye(chart, look_ahead=look_ahead, depth=depth)
    player = Player(
        eye=eye,
        reservoir=NullReservoir(size=LANE_COUNT * depth),
        readout=NearBinReadout(),
        hands=NullHands(),
    )
    actions: list[Action] = []
    t = 0.0
    end = chart.duration_seconds + look_ahead
    while t <= end + 1e-9:
        actions.append(player.tick(t))
        t += step
    return actions
