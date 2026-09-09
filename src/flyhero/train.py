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


class LinearReadout:
    """Learned map from reservoir state to frets + strum. ``W`` stays frozen."""

    def __init__(
        self,
        weights: tuple[tuple[float, ...], ...],
        *,
        threshold: float = 0.5,
    ) -> None:
        if len(weights) != LANE_COUNT + 1:
            raise ValueError("need five fret rows plus one strum row")
        width = len(weights[0])
        if width < 2:
            raise ValueError("each row needs state weights plus a bias")
        if any(len(row) != width for row in weights):
            raise ValueError("weight rows must share a length")
        if not 0.0 <= threshold <= 1.0:
            raise ValueError("threshold must be in [0, 1]")
        self.weights = weights
        self.threshold = threshold

    def act(self, state: list[float] | tuple[float, ...]) -> Action:
        width = len(self.weights[0]) - 1
        values = [float(v) for v in state]
        if len(values) < width:
            values.extend(0.0 for _ in range(width - len(values)))
        elif len(values) > width:
            values = values[:width]
        values.append(1.0)
        outs = [sum(w * x for w, x in zip(row, values)) for row in self.weights]
        frets = tuple(out >= self.threshold for out in outs[:LANE_COUNT])
        return Action.from_frets(frets, outs[LANE_COUNT] >= self.threshold)


def _transpose(matrix: list[list[float]]) -> list[list[float]]:
    return [list(row) for row in zip(*matrix)]


def _matvec(matrix: list[list[float]], vector: list[float]) -> list[float]:
    return [sum(row[j] * vector[j] for j in range(len(vector))) for row in matrix]


def _matmul(left: list[list[float]], right: list[list[float]]) -> list[list[float]]:
    cols = _transpose(right)
    return [[sum(a * b for a, b in zip(row, col)) for col in cols] for row in left]


def _solve(matrix: list[list[float]], vector: list[float]) -> list[float]:
    n = len(matrix)
    aug = [row[:] + [vector[i]] for i, row in enumerate(matrix)]
    for col in range(n):
        pivot = max(range(col, n), key=lambda r: abs(aug[r][col]))
        aug[col], aug[pivot] = aug[pivot], aug[col]
        diag = aug[col][col]
        if abs(diag) < 1e-12:
            raise ValueError("singular teach matrix")
        scale = 1.0 / diag
        aug[col] = [v * scale for v in aug[col]]
        for row in range(n):
            if row == col:
                continue
            factor = aug[row][col]
            aug[row] = [aug[row][c] - factor * aug[col][c] for c in range(n + 1)]
    return [row[-1] for row in aug]


def _ridge_solve(design: list[list[float]], target: list[float], ridge: float) -> list[float]:
    xt = _transpose(design)
    gram = _matmul(xt, design)
    for i in range(len(gram)):
        gram[i][i] += ridge
    return _solve(gram, _matvec(xt, target))


def fit_linear_readout(samples: list[Sample], *, ridge: float = 1e-3) -> LinearReadout:
    """Least-squares readout on highway pictures. This is the teach step."""
    if not samples:
        raise ValueError("need samples to teach the readout")
    if ridge <= 0:
        raise ValueError("ridge must be positive")
    design: list[list[float]] = []
    targets: list[list[float]] = []
    for sample in samples:
        row = list(sample.frame.as_vector())
        row.append(1.0)
        design.append(row)
        targets.append(
            [1.0 if held else 0.0 for held in sample.action.frets]
            + [1.0 if sample.action.strum else 0.0]
        )
    weights = []
    for column in range(LANE_COUNT + 1):
        y = [row[column] for row in targets]
        weights.append(tuple(_ridge_solve(design, y, ridge)))
    return LinearReadout(tuple(weights))


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
