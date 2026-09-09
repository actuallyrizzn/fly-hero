from __future__ import annotations

from pathlib import Path

import pytest
from PIL import Image

from flyhero.capture import WindowBox, crop_to_box, grab_clonehero
from flyhero.pipewire import (
    ScreenCastSession,
    detect_connector,
    grab_desktop_frame,
    grab_pipewire_node,
    mutter_open,
)
from flyhero.visibility import is_visible, mean_luma, require_visible


def _rgb(color, size=(64, 48)) -> Image.Image:
    return Image.new("RGB", size, color)


def test_visibility_rejects_black_accepts_picture():
    black = _rgb((0, 0, 0))
    assert mean_luma(black) == 0
    assert is_visible(black) is False
    with pytest.raises(RuntimeError, match="black"):
        require_visible(black)
    picture = _rgb((40, 80, 120))
    assert is_visible(picture) is True
    assert require_visible(picture.convert("RGBA")).mode == "RGB"


def test_detect_connector_prefers_edp(tmp_path: Path):
    drm = tmp_path / "drm"
    for name, status in (
        ("card1-HDMI-A-1", "connected"),
        ("card1-eDP-1", "connected"),
        ("card1-DP-1", "disconnected"),
        ("card1", "connected"),
    ):
        entry = drm / name
        entry.mkdir(parents=True)
        (entry / "status").write_text(status + "\n", encoding="utf-8")
    assert detect_connector(drm) == "eDP-1"


def test_detect_connector_first_connected_without_edp(tmp_path: Path):
    drm = tmp_path / "drm"
    entry = drm / "card0-HDMI-A-1"
    entry.mkdir(parents=True)
    (entry / "status").write_text("connected\n", encoding="utf-8")
    assert detect_connector(drm) == "HDMI-A-1"
    empty = tmp_path / "empty"
    empty.mkdir()
    assert detect_connector(empty) == "eDP-1"
    assert detect_connector(tmp_path / "missing") == "eDP-1"


def test_grab_pipewire_node_reads_png(tmp_path: Path, monkeypatch):
    painted = _rgb((90, 20, 20), (32, 24))

    def runner(cmd, **kwargs):
        assert any(part.startswith("target-object=") for part in cmd)
        out = Path(cmd[-1].split("=", 1)[1])
        painted.save(out)

        class Result:
            returncode = 0
            stderr = ""
            stdout = ""

        return Result()

    image = grab_pipewire_node(17, runner=runner)
    assert image.size == (32, 24)
    assert image.mode == "RGB"
    with pytest.raises(ValueError, match="positive"):
        grab_pipewire_node(0, runner=runner)


def test_grab_pipewire_node_gst_failure():
    class Result:
        returncode = 1
        stderr = "no node"
        stdout = ""

    with pytest.raises(RuntimeError, match="no node"):
        grab_pipewire_node(3, runner=lambda *a, **k: Result())


def test_grab_pipewire_node_missing_png():
    class Result:
        returncode = 0
        stderr = ""
        stdout = "ok"

    with pytest.raises(RuntimeError, match="pipewiresrc"):
        grab_pipewire_node(3, runner=lambda *a, **k: Result())


def test_screencast_session_reuses_node():
    frames = [_rgb((10, 10, 200)), _rgb((200, 10, 10))]

    def opener(*, connector=None):
        assert connector in (None, "eDP-1")
        return object(), "/stream", 44

    def gst(node_id):
        assert node_id == 44
        return frames.pop(0)

    session = ScreenCastSession(opener=opener, gst=gst)
    first = session.grab()
    second = session.grab()
    assert first.getpixel((0, 0))[2] == 200
    assert second.getpixel((0, 0))[0] == 200
    session.close()
    session.close()


def test_screencast_context_and_stop_error():
    picture = _rgb((12, 90, 12))

    class Boom:
        def Stop(self):
            raise RuntimeError("already gone")

    def opener(*, connector=None):
        assert connector == "HDMI-A-1"
        return Boom(), "/s", 8

    with ScreenCastSession(connector="HDMI-A-1", opener=opener, gst=lambda n: picture) as session:
        assert session.node_id == 8
        assert grab_desktop_frame(session=session).size == picture.size


def test_grab_desktop_frame_opens_owned(monkeypatch):
    picture = _rgb((80, 80, 20))

    class Fake(ScreenCastSession):
        def __init__(self, **kwargs):
            super().__init__(
                opener=lambda **k: (object(), "/s", 1),
                gst=lambda n: picture,
            )

    monkeypatch.setattr("flyhero.pipewire.ScreenCastSession", Fake)
    assert grab_desktop_frame().size == picture.size


def test_mutter_open_injected_bus():
    class FakeDbus:
        class UInt32(int):
            pass

        class Interface:
            def __init__(self, obj, name):
                self.obj = obj
                self.name = name

            def CreateSession(self, props):
                return "/session/1"

            def RecordMonitor(self, connector, props):
                assert connector == "eDP-1"
                return "/stream/1"

            def Start(self):
                self.started = True

        @staticmethod
        def get_object(name, path):
            return path

    import flyhero.pipewire as pw

    monkeypatch_dbus = FakeDbus
    # mutter_open imports dbus locally — inject by passing bus + wait_node
    bus = FakeDbus()

    class Bus:
        def get_object(self, name, path):
            return path

    # Patch dbus.Interface used inside mutter_open
    import types
    import sys

    fake_mod = types.ModuleType("dbus")
    fake_mod.Interface = FakeDbus.Interface
    fake_mod.UInt32 = FakeDbus.UInt32
    fake_mod.SessionBus = lambda: Bus()
    sys.modules["dbus"] = fake_mod
    import flyhero.pipewire as pw

    real_wait = pw._start_and_wait_node
    try:
        session, stream, node = mutter_open(bus=Bus(), wait_node=lambda b, p: 99, connector="eDP-1")
        assert stream == "/stream/1"
        assert node == 99
        session.Start()
        pw._start_and_wait_node = lambda bus, session, path, timeout_ms=5000: 55
        session2, stream2, node2 = mutter_open(bus=Bus(), connector="eDP-1")
        assert stream2 == "/stream/1"
        assert node2 == 55
    finally:
        pw._start_and_wait_node = real_wait
        sys.modules.pop("dbus", None)


def test_mutter_open_requires_node():
    import types
    import sys

    class Interface:
        def __init__(self, obj, name):
            pass

        def CreateSession(self, props):
            return "/s"

        def RecordMonitor(self, connector, props):
            return "/t"

        def Start(self):
            pass

    fake_mod = types.ModuleType("dbus")
    fake_mod.Interface = Interface
    fake_mod.UInt32 = lambda n: n
    sys.modules["dbus"] = fake_mod

    class Bus:
        def get_object(self, name, path):
            return path

    try:
        with pytest.raises(RuntimeError, match="PipeWire node"):
            mutter_open(bus=Bus(), wait_node=lambda b, p: 0, connector="eDP-1")
    finally:
        sys.modules.pop("dbus", None)


def test_start_and_wait_node_signal():
    import types
    import sys

    from flyhero import pipewire as pw

    stored = []

    class Loop:
        def quit(self):
            self.quit_called = True

        def run(self):
            self.ran = True

    class GLib:
        @staticmethod
        def MainLoop():
            return Loop()

        @staticmethod
        def timeout_add(ms, fn):
            return 1

    class Bus:
        def add_signal_receiver(self, cb, **kwargs):
            stored.append(cb)

    class Session:
        def Start(self):
            stored[0](77)

    gi = types.ModuleType("gi")
    repo = types.ModuleType("gi.repository")
    repo.GLib = GLib
    gi.repository = repo
    sys.modules["gi"] = gi
    sys.modules["gi.repository"] = repo
    try:
        node = pw._start_and_wait_node(Bus(), Session(), "/stream/1")
        assert node == 77

        class Quiet:
            def Start(self):
                pass

        assert pw._start_and_wait_node(Bus(), Quiet(), "/stream/1") == 0
    finally:
        sys.modules.pop("gi.repository", None)
        sys.modules.pop("gi", None)


def test_crop_and_grab_clonehero_pipewire():
    monitor = Image.new("RGB", (200, 100), (8, 8, 8))
    monitor.paste(Image.new("RGB", (80, 40), (200, 30, 30)), (40, 20))
    box = WindowBox(left=40, top=20, width=80, height=40)
    cropped = crop_to_box(monitor, box)
    assert cropped.size == (80, 40)
    assert cropped.getpixel((0, 0))[0] == 200
    tiny = crop_to_box(monitor, WindowBox(0, 0, 1, 1))
    assert tiny.size == monitor.size
    with pytest.raises(ValueError, match="positive"):
        crop_to_box(monitor, box, screen_size=(0, 10))

    scaled = crop_to_box(monitor, WindowBox(40, 20, 80, 40), screen_size=(400, 200))
    assert scaled.size[0] == 40

    image = grab_clonehero(
        display=":3",
        frame_grabber=lambda: monitor,
        box_finder=lambda title="Clone Hero": box,
    )
    assert image.size == (80, 40)

    full = grab_clonehero(
        frame_grabber=lambda: monitor,
        box_finder=lambda **k: (_ for _ in ()).throw(FileNotFoundError("gone")),
    )
    assert full.size == monitor.size

    no_kw = grab_clonehero(
        frame_grabber=lambda: monitor,
        box_finder=lambda: box,
    )
    assert no_kw.size == (80, 40)

    rgba = Image.new("RGBA", (80, 40), (10, 20, 30, 255))
    assert crop_to_box(rgba, WindowBox(0, 0, 80, 40)).mode == "RGB"
