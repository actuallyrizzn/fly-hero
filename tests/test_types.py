from __future__ import annotations

import pytest

from flyhero.types import Action, FeatureFrame, Lane


def test_empty_frame_is_zero_vector():
    frame = FeatureFrame.empty(depth=2)
    assert frame.depth == 2
    assert frame.as_vector() == (0.0,) * 10
    assert frame.t_seconds == 0.0


def test_from_rows_round_trip():
    frame = FeatureFrame.from_rows(
        [
            [1.0, 0.0],
            [0.0, 1.0],
            [0.5, 0.5],
            [0.0, 0.0],
            [0.25, 0.75],
        ],
        t_seconds=1.5,
    )
    assert frame.cells[Lane.GREEN][0] == 1.0
    assert frame.t_seconds == 1.5
    assert len(frame.as_vector()) == 10


def test_frame_rejects_wrong_lane_count():
    with pytest.raises(ValueError, match="5 lanes"):
        FeatureFrame(cells=((0.0,),), t_seconds=0.0)


def test_frame_rejects_ragged_depth():
    with pytest.raises(ValueError, match="same depth"):
        FeatureFrame.from_rows([[0.0], [0.0, 1.0], [0.0], [0.0], [0.0]])


def test_frame_rejects_empty_depth():
    with pytest.raises(ValueError, match="depth"):
        FeatureFrame(cells=(tuple(),) * 5, t_seconds=0.0)


def test_frame_rejects_out_of_range():
    with pytest.raises(ValueError, match="out of range"):
        FeatureFrame.from_rows([[1.1], [0.0], [0.0], [0.0], [0.0]])


def test_action_idle_and_from_frets():
    idle = Action.idle()
    assert idle.strum is False
    assert idle.frets == (False,) * 5
    held = Action.from_frets([True, False, False, False, False], True)
    assert held.strum is True
    assert held.frets[Lane.GREEN] is True


def test_action_rejects_wrong_fret_count():
    with pytest.raises(ValueError, match="5 frets"):
        Action(frets=(True,), strum=False)
