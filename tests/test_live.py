from __future__ import annotations

from pathlib import Path

import pytest

from flyhero.chart import load_chart
from flyhero.live import play_live
from flyhero.uinput_hands import RecordingHands

FIXTURE = Path(__file__).parent / "fixtures" / "midtempo.chart"


class FakeClock:
    def __init__(self) -> None:
        self.t = 0.0

    def now(self) -> float:
        return self.t

    def sleep(self, delay: float) -> None:
        self.t += delay


def test_load_easy_track_is_shorter():
    easy = load_chart(FIXTURE, track="EasySingle")
    expert = load_chart(FIXTURE, track="ExpertSingle")
    assert easy.name == expert.name
    assert len(easy.notes) == 2
    assert len(expert.notes) == 5
    assert easy.notes[0].lane == 0


def test_play_live_countdown_then_first_green():
    chart = load_chart(FIXTURE, track="EasySingle")
    hands = RecordingHands()
    clock = FakeClock()
    actions = play_live(
        chart,
        hands,
        look_ahead=1.0,
        depth=4,
        step=0.25,
        countdown=0.5,
        clock=clock.now,
        sleeper=clock.sleep,
    )
    assert actions[0].strum is False
    # After countdown, t=0.50 chart time is the green gem.
    assert any(a.frets[0] and a.strum for a in actions)
    assert "0.50 1 down" in hands.render()


def test_play_live_rejects_bad_timing():
    chart = load_chart(FIXTURE, track="EasySingle")
    with pytest.raises(ValueError, match="step"):
        play_live(chart, RecordingHands(), step=0, clock=lambda: 0.0, sleeper=lambda _: None)
    with pytest.raises(ValueError, match="countdown"):
        play_live(chart, RecordingHands(), countdown=-1, clock=lambda: 0.0, sleeper=lambda _: None)
