"""Doom-fly prosthesis: strike-zone → DN-VNC leg inject → fret twitches.

The larva connectome has no MN/leg labels. DN-VNC (descending to VNC) is the
motor-adjacent pool that twitches hard when driven directly. Sensory→DN-VNC
through the default random projection is ~100× too weak for a split-second
fret edge — so the prosthesis *is* the glasses: we inject onto chosen DN-VNC
neurons when a gem occupies the near (strike) bin.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from flyhero.connectome import Connectome, load_connectome
from flyhero.reservoir import EchoReservoir
from flyhero.types import LANE_COUNT, Action, FeatureFrame

LEG_COUNT = LANE_COUNT + 1  # five frets + strum


def pick_leg_neurons(
    connectome: Connectome | None = None,
    *,
    count: int = LEG_COUNT,
    seed: int = 0,
) -> tuple[int, ...]:
    """Pick stable DN-VNC indices to use as virtual legs."""
    graph = connectome or load_connectome()
    pool = graph.neurons_of_type("DN-VNC")
    if pool.size < count:
        raise ValueError(f"need at least {count} DN-VNC neurons, have {pool.size}")
    rng = np.random.default_rng(seed)
    # Deterministic subset — first `count` after a seeded shuffle so we can
    # re-roll legs without depending on CSV row order forever.
    order = np.arange(pool.size)
    rng.shuffle(order)
    chosen = pool[order[:count]]
    return tuple(int(i) for i in chosen)


def build_leg_reservoir(
    *,
    seed: int = 0,
    amplitude_scale: float = 2.0,
    connectome: Connectome | None = None,
) -> tuple[EchoReservoir, tuple[int, ...]]:
    """Echo state whose only inputs are the six DN-VNC legs."""
    graph = connectome or load_connectome()
    legs = pick_leg_neurons(graph, count=LEG_COUNT, seed=seed)
    reservoir = EchoReservoir(
        graph.weights,
        inputs=LEG_COUNT,
        input_neurons=legs,
        seed=seed,
        input_scale=amplitude_scale,
    )
    return reservoir, legs


@dataclass
class LegProsthesis:
    """Same-tick reflex: highway occupancy → leg inject → threshold frets.

    Live pixel eye lags (~0.5s snapshots). Holding frets only on the thin
    strike bin misses notes that the camera sees mid-approach and never
    samples on the line. So:

    - **Frets:** any occupied bin in that lane (approach prep).
    - **Strum:** near bin *or* the next-nearest approach bin (bin 1) so a
      late camera still edges through the hit window.

    ``W`` stays frozen — this is still the wired glasses path, just with
    depth-aware triggers.
    """

    reservoir: EchoReservoir
    legs: tuple[int, ...]
    near_threshold: float = 0.5
    twitch_threshold: float = 0.25
    amplitude: float = 5.0
    strum_farness: int = 4  # bins 0..4 — live snapshots rarely catch bin 0 alone
    _near_was_hot: bool = False
    _strum_pulse_high: bool = False

    def __post_init__(self) -> None:
        if len(self.legs) != LEG_COUNT:
            raise ValueError(f"need {LEG_COUNT} legs, got {len(self.legs)}")
        if self.reservoir.inputs != LEG_COUNT:
            raise ValueError("reservoir inputs must match leg count")
        if not 0.0 <= self.near_threshold <= 1.0:
            raise ValueError("near_threshold must be in [0, 1]")
        if not 0.0 <= self.twitch_threshold <= 1.0:
            raise ValueError("twitch_threshold must be in [0, 1]")
        if self.strum_farness < 0:
            raise ValueError("strum_farness must be >= 0")

    @classmethod
    def create(
        cls,
        *,
        seed: int = 0,
        near_threshold: float = 0.5,
        twitch_threshold: float = 0.25,
        amplitude: float = 5.0,
        strum_farness: int = 4,
    ) -> LegProsthesis:
        reservoir, legs = build_leg_reservoir(seed=seed)
        return cls(
            reservoir=reservoir,
            legs=legs,
            near_threshold=near_threshold,
            twitch_threshold=twitch_threshold,
            amplitude=amplitude,
            strum_farness=strum_farness,
        )

    def reset(self) -> None:
        self.reservoir.reset()
        self._near_was_hot = False
        self._strum_pulse_high = False

    def drive_from_frame(self, frame: FeatureFrame) -> np.ndarray:
        """Highway picture → six floats. Frets from any depth; strum from near strip."""
        drive = np.zeros(LEG_COUNT, dtype=np.float32)
        hot = False
        depth = frame.depth
        strum_limit = min(self.strum_farness, max(0, depth - 1))
        for lane in range(LANE_COUNT):
            row = frame.cells[lane]
            if any(float(row[d]) >= self.near_threshold for d in range(depth)):
                drive[lane] = np.float32(self.amplitude)
            if any(float(row[d]) >= self.near_threshold for d in range(strum_limit + 1)):
                hot = True
        if hot:
            drive[LANE_COUNT] = np.float32(self.amplitude)  # strum leg
        return drive

    def act_from_state(
        self,
        state: np.ndarray | list[float],
        *,
        drive: np.ndarray | None = None,
        strum_edge: bool = True,
    ) -> Action:
        """Map activity to frets + strum.

        When ``drive`` is present (pixel/ChartEye path), frets and strum intent
        come from that drive — the DN-VNC reservoir mis-maps multi-leg inject
        (correct leg goes negative; neighbors twitch). Reservoir still steps so
        side-panel viz can watch DN-VNC, but buttons follow the eye.

        Without ``drive``, fall back to reservoir twitches alone.
        """
        if drive is not None:
            frets = tuple(bool(float(drive[i]) > 0.0) for i in range(LANE_COUNT))
            want_strum = bool(float(drive[LANE_COUNT]) > 0.0)
        else:
            frets = tuple(
                float(state[self.legs[i]]) >= self.twitch_threshold for i in range(LANE_COUNT)
            )
            want_strum = float(state[self.legs[LANE_COUNT]]) >= self.twitch_threshold
        if not strum_edge:
            self._near_was_hot = bool(want_strum)
            return Action.from_frets(frets, want_strum)
        if want_strum:
            strum = not self._strum_pulse_high
            self._strum_pulse_high = strum
        else:
            strum = False
            self._strum_pulse_high = False
        self._near_was_hot = bool(want_strum)
        return Action.from_frets(frets, strum)

    def tick(self, frame: FeatureFrame, *, gate_drive: bool = True) -> Action:
        drive = self.drive_from_frame(frame)
        state = self.reservoir.step(drive)
        # Always pass drive so frets track the eye; reservoir is for viz/science.
        return self.act_from_state(state, drive=drive if gate_drive else None)


class ProsthesisPlayer:
    """eye → LegProsthesis → hands (bypasses the highway→sensory Player path)."""

    def __init__(self, eye, prosthesis: LegProsthesis, hands) -> None:
        self.eye = eye
        self.prosthesis = prosthesis
        self.hands = hands

    def reset(self) -> None:
        self.prosthesis.reset()

    def tick(self, t_seconds: float) -> Action:
        frame = self.eye.see(t_seconds)
        action = self.prosthesis.tick(frame)
        self.hands.apply(action)
        return action
