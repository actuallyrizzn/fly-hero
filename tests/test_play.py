from __future__ import annotations

from pathlib import Path

import pytest

from flyhero.chart import load_chart
from flyhero.guitar import EV_KEY, GuitarMap, KeyEvent, diff_action
from flyhero.pixel import render_highway
from flyhero.pixel_eye import PixelEye
from flyhero.play import record_chart
from flyhero.train import NearBinReadout
from flyhero.types import Action
from flyhero.uinput_hands import DeviceHands, RecordingHands, open_uinput

FIXTURE = Path(__file__).parent / "fixtures" / "midtempo.chart"

MIDTEMPO_EVENTS = "\n".join(
    [
        "0.50 1 down",
        "0.50 down down",
        "0.75 1 up",
        "0.75 down up",
        "1.00 2 down",
        "1.00 down down",
        "1.25 2 up",
        "1.25 down up",
        "1.50 3 down",
        "1.50 down down",
        "1.75 3 up",
        "1.75 down up",
        "2.00 1 down",
        "2.00 4 down",
        "2.00 down down",
        "2.25 1 up",
        "2.25 4 up",
        "2.25 down up",
    ]
)


class FakeDevice:
    def __init__(self, codes=None) -> None:
        self.codes = codes
        self.writes: list[tuple] = []

    def write(self, etype, code, value) -> None:
        self.writes.append((etype, code, value))

    def syn(self) -> None:
        self.writes.append(("syn", 0, 0))


def test_midtempo_recorded_song_is_scorable():
    log = record_chart(load_chart(FIXTURE), step=0.25, look_ahead=1.0, depth=4)
    assert log.render() == MIDTEMPO_EVENTS
    assert any(a.strum for a in log.song_actions)


def test_pixel_eye_strike_presses_green():
    chart = load_chart(FIXTURE)
    poc = record_chart(chart, step=0.5, look_ahead=1.0, depth=4)
    strike = next(a for a in poc.song_actions if a.frets[0])
    from flyhero.highway import encode_highway
    from flyhero.player import Player
    from flyhero.reservoir import NullReservoir

    frame = encode_highway(chart, 0.5, look_ahead=1.0, depth=4)
    eye = PixelEye(render_highway(frame), depth=4)
    hands = RecordingHands()
    player = Player(eye, NullReservoir(size=20), NearBinReadout(), hands)
    hands.set_time(0.5)
    action = player.tick(0.5)
    assert action == strike
    assert hands.render() == "0.50 1 down\n0.50 down down"


def test_diff_and_device_edges():
    mapping = GuitarMap()
    idle = Action.idle()
    green = Action.from_frets((True, False, False, False, False), True)
    edges = diff_action(idle, green, mapping)
    assert edges == [(2, True), (108, True)]
    fake = FakeDevice()
    hands = DeviceHands(fake, mapping)
    hands.apply(green)
    assert (EV_KEY, 2, 1) in fake.writes
    assert ("syn", 0, 0) in fake.writes
    hands.apply(idle)
    assert (EV_KEY, 2, 0) in fake.writes
    with pytest.raises(ValueError, match="device"):
        DeviceHands(None)


def test_open_uinput_factory_and_map_guard():
    device = open_uinput(factory=lambda codes: FakeDevice(codes))
    assert device.codes == [2, 3, 4, 5, 6, 108]
    with pytest.raises(ValueError, match="fret codes"):
        GuitarMap(fret_codes=(1, 2))
    event = KeyEvent(1.5, "1", False)
    assert event.render() == "1.50 1 up"


def test_record_rejects_bad_step():
    with pytest.raises(ValueError, match="step"):
        record_chart(load_chart(FIXTURE), step=0)


def test_record_accepts_injected_hands():
    chart = load_chart(FIXTURE)
    rec = RecordingHands()
    log = record_chart(chart, step=0.5, look_ahead=1.0, depth=4, hands=rec)
    assert log is rec
    assert rec.render()
    fake = FakeDevice()
    record_chart(chart, step=0.5, look_ahead=1.0, depth=4, hands=DeviceHands(fake))
    assert fake.writes


def test_open_uinput_evdev(monkeypatch):
    import sys
    from types import ModuleType

    class FakeUInput:
        def __init__(self, cap, name=""):
            self.cap = cap
            self.name = name

    class Codes:
        EV_KEY = 1

    mod = ModuleType("evdev")
    mod.UInput = FakeUInput
    mod.ecodes = Codes
    monkeypatch.setitem(sys.modules, "evdev", mod)
    device = open_uinput()
    assert device.name == "Fly Hero guitar"


def test_open_uinput_missing_evdev(monkeypatch):
    import builtins

    real = builtins.__import__

    def blocked(name, *args, **kwargs):
        if name == "evdev":
            raise ImportError("missing")
        return real(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", blocked)
    with pytest.raises(RuntimeError, match="evdev"):
        open_uinput()


def test_device_without_syn_writes_syn_report():
    class WriteOnly:
        def __init__(self) -> None:
            self.writes = []

        def write(self, etype, code, value) -> None:
            self.writes.append((etype, code, value))

    hands = DeviceHands(WriteOnly())
    hands.apply(Action.from_frets((True, False, False, False, False), False))
    assert hands.device.writes[-1][0] == 0
