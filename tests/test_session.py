from __future__ import annotations

from pathlib import Path

import pytest

from flyhero.chart import load_chart, pick_track
from flyhero.detect import paint_receptors
from flyhero.launch import load_song_argv
from flyhero.session import run_live, run_offline, run_offline_path
from flyhero.uinput_hands import DeviceHands, RecordingHands, TeeHands

FIXTURE = Path(__file__).parent / "fixtures" / "midtempo.chart"


class Clock:
    def __init__(self) -> None:
        self.t = 0.0

    def now(self) -> float:
        return self.t

    def sleep(self, delay: float) -> None:
        self.t += delay


def test_offline_fixture_session_is_accepted():
    result = run_offline_path(FIXTURE, track="ExpertSingle")
    assert result.track == "ExpertSingle"
    assert result.score.accepted()
    assert result.log.events


def test_offline_chart_object():
    chart = load_chart(FIXTURE)
    result = run_offline(chart)
    assert result.score.hits == result.score.notes


def test_pick_track_auto_and_missing():
    text = FIXTURE.read_text(encoding="utf-8")
    assert pick_track(text, "auto") == "EasySingle"
    assert pick_track(text, "ExpertSingle") == "ExpertSingle"
    with pytest.raises(ValueError, match="no \\[Nope\\]"):
        pick_track(text, "Nope")
    with pytest.raises(ValueError, match="no guitar"):
        pick_track("[Song]\n{\n}\n", "auto")


def test_live_session_uses_loader_not_bot():
    chart = load_chart(FIXTURE)
    started: list[list[str]] = []
    stopped: list[str] = []

    def start(argv):
        started.append(list(argv))
        return "proc"

    clock = Clock()
    hands = RecordingHands()
    result = run_live(
        chart,
        hands,
        start=start,
        grab=paint_receptors,
        argv=load_song_argv(FIXTURE),
        countdown=0.0,
        look_ahead=1.0,
        depth=4,
        step=0.25,
        window=0.3,
        waiter=lambda _grab: paint_receptors(),
        stopper=lambda proc: stopped.append(proc),
        clock=clock.now,
        sleeper=clock.sleep,
    )
    assert "--player" not in started[0]
    assert "--song" in started[0]
    assert stopped == ["proc"]
    assert result.score.accepted()


def test_live_requires_grabber():
    with pytest.raises(ValueError, match="grabber"):
        run_live(load_chart(FIXTURE), RecordingHands(), start=lambda argv: None)


def test_live_terminates_process_without_stopper():
    class Proc:
        def __init__(self) -> None:
            self.terminated = False

        def terminate(self) -> None:
            self.terminated = True

    proc = Proc()
    clock = Clock()
    taught = run_offline(load_chart(FIXTURE)).readout
    run_live(
        load_chart(FIXTURE),
        RecordingHands(),
        start=lambda argv: proc,
        grab=paint_receptors,
        argv=["clonehero", "--song", "/tmp/tune"],
        countdown=0.0,
        look_ahead=1.0,
        depth=4,
        step=0.5,
        window=0.3,
        readout=taught,
        waiter=lambda _grab: paint_receptors(),
        clock=clock.now,
        sleeper=clock.sleep,
    )
    assert proc.terminated is True


def test_live_scores_tee_hands_log():
    class FakeDevice:
        def write(self, *args) -> None:
            return None

        def syn(self) -> None:
            return None

    clock = Clock()
    taught = run_offline(load_chart(FIXTURE)).readout
    hands = TeeHands(DeviceHands(FakeDevice()))
    result = run_live(
        load_chart(FIXTURE),
        hands,
        start=lambda argv: type("P", (), {"terminate": lambda self: None})(),
        grab=paint_receptors,
        argv=["clonehero", "--song", "/tmp/tune"],
        countdown=0.0,
        look_ahead=1.0,
        depth=4,
        step=0.25,
        window=0.3,
        readout=taught,
        waiter=lambda _grab: paint_receptors(),
        clock=clock.now,
        sleeper=clock.sleep,
    )
    assert result.log is hands.log
    assert result.score.accepted()
