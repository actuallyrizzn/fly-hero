from __future__ import annotations

import pytest

from flyhero.eye import NullEye
from flyhero.hands import NullHands
from flyhero.player import Player
from flyhero.readout import NullReadout, ThresholdReadout
from flyhero.reservoir import NullReservoir
from flyhero.types import FeatureFrame


class ScriptedEye:
    def __init__(self, frame: FeatureFrame) -> None:
        self.frame = frame

    def see(self, t_seconds: float) -> FeatureFrame:
        assert t_seconds >= 0
        return self.frame


def test_null_eye_empty():
    eye = NullEye(depth=3)
    frame = eye.see(2.0)
    assert frame.depth == 3
    assert frame.t_seconds == 2.0
    assert all(v == 0.0 for v in frame.as_vector())


def test_null_eye_rejects_bad_depth():
    with pytest.raises(ValueError):
        NullEye(depth=0)


def test_reservoir_pad_truncate_reset():
    res = NullReservoir(size=4)
    assert res.size == 4
    assert res.step([1.0, 2.0]) == (1.0, 2.0, 0.0, 0.0)
    assert res.step([9.0, 8.0, 7.0, 6.0, 5.0]) == (9.0, 8.0, 7.0, 6.0)
    res.reset()
    assert res.step([]) == (0.0, 0.0, 0.0, 0.0)


def test_reservoir_rejects_bad_size():
    with pytest.raises(ValueError):
        NullReservoir(size=0)


def test_null_readout_idle_and_empty_state():
    out = NullReadout()
    assert out.act([0.1, 0.2]).strum is False
    with pytest.raises(ValueError, match="non-empty"):
        out.act([])


def test_threshold_readout():
    out = ThresholdReadout(threshold=0.5)
    action = out.act([0.9, 0.1, 0.5, 0.0, 0.0, 99.0])
    assert action.frets == (True, False, True, False, False)
    assert action.strum is True
    with pytest.raises(ValueError, match="at least 5"):
        out.act([0.1])
    with pytest.raises(ValueError, match="threshold"):
        ThresholdReadout(threshold=1.5)


def test_player_tick_drives_hands():
    frame = FeatureFrame.from_rows([[1.0], [0.0], [0.0], [0.0], [0.0]])
    hands = NullHands()
    player = Player(
        eye=ScriptedEye(frame),
        reservoir=NullReservoir(size=5),
        readout=ThresholdReadout(threshold=0.5),
        hands=hands,
    )
    action = player.tick(0.0)
    assert action.frets[0] is True
    assert action.strum is True
    assert hands.calls == 1
    assert hands.last == action
    player.reset()
    quiet = FeatureFrame.empty(depth=1)
    player.eye = ScriptedEye(quiet)
    idle = player.tick(1.0)
    assert idle.strum is False
    assert hands.calls == 2
