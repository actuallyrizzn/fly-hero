from __future__ import annotations

from pathlib import Path

import pytest
from PIL import Image

from flyhero.pipewire import ScreenCastSession, grab_desktop_frame
from flyhero.shellcast import (
    ShellScreencast,
    extract_frame,
    snapshot_frame,
    start_screencast,
    stop_screencast,
)


def _rgb(color, size=(64, 48)) -> Image.Image:
    return Image.new("RGB", size, color)


def test_extract_frame_reads_png(tmp_path: Path):
    painted = _rgb((20, 80, 160), (32, 24))
    webm = tmp_path / "live.webm"
    webm.write_bytes(b"x" * 80)

    def runner(cmd, **kwargs):
        out = Path(cmd[-1])
        painted.save(out)

        class Result:
            returncode = 0
            stderr = ""
            stdout = ""

        return Result()

    image = extract_frame(webm, runner=runner)
    assert image.size == (32, 24)
    assert image.getpixel((0, 0))[2] == 160


def test_extract_frame_rejects_empty(tmp_path: Path):
    from flyhero.shellcast import resolve_cast_file

    missing = tmp_path / "no.webm"
    with pytest.raises(RuntimeError, match="empty"):
        extract_frame(missing)
    empty = tmp_path / "empty.webm"
    empty.write_bytes(b"tiny")
    with pytest.raises(RuntimeError, match="empty"):
        extract_frame(empty)
    stem = tmp_path / "live"
    sibling = tmp_path / "live.webm"
    sibling.write_bytes(b"x" * 80)
    assert resolve_cast_file(stem) == sibling


def test_extract_frame_ffmpeg_failure(tmp_path: Path):
    webm = tmp_path / "live.webm"
    webm.write_bytes(b"x" * 80)

    class Result:
        returncode = 1
        stderr = "no decoder"
        stdout = ""

    with pytest.raises(RuntimeError, match="no decoder"):
        extract_frame(webm, runner=lambda *a, **k: Result())


def test_shell_screencast_retries_empty_then_grabs():
    calls = {"n": 0}

    def extractor(webm):
        calls["n"] += 1
        if calls["n"] < 3:
            raise RuntimeError("Screencast file is empty")
        return _rgb((1, 2, 3))

    slept = []
    session = ShellScreencast(
        starter=lambda dest, framerate=15: Path("/tmp/r.webm"),
        stopper=lambda: True,
        extractor=extractor,
        sleeper=slept.append,
    )
    assert session.grab().getpixel((0, 0)) == (1, 2, 3)
    assert calls["n"] == 3
    assert slept == [0.25, 0.25]
    session.close()


def test_shell_screencast_reuses_extract():
    frames = [_rgb((10, 10, 200)), _rgb((200, 10, 10))]

    def starter(dest, framerate=15):
        assert framerate == 12
        return Path("/tmp/flyhero-live.webm")

    def extractor(webm):
        assert webm == Path("/tmp/flyhero-live.webm")
        return frames.pop(0)

    session = ShellScreencast(starter=starter, stopper=lambda: True, extractor=extractor, framerate=12)
    first = session.grab()
    second = session.grab()
    assert first.getpixel((0, 0))[2] == 200
    assert second.getpixel((0, 0))[0] == 200
    session.close()
    session.close()


def test_extract_frame_timeout(tmp_path: Path):
    import subprocess

    webm = tmp_path / "live.webm"
    webm.write_bytes(b"x" * 80)

    def runner(*a, **k):
        raise subprocess.TimeoutExpired(cmd="ffmpeg", timeout=1)

    with pytest.raises(RuntimeError, match="timed out"):
        extract_frame(webm, runner=runner)


def test_shell_context_manager():
    picture = _rgb((8, 8, 90))
    with ShellScreencast(
        starter=lambda dest, framerate=15: Path("/tmp/y.webm"),
        stopper=lambda: True,
        extractor=lambda webm: picture,
    ) as session:
        assert session.grab().size == picture.size


def test_screen_session_defaults_to_shell():
    picture = _rgb((90, 40, 10))
    shell = ShellScreencast(
        starter=lambda dest, framerate=15: Path("/tmp/x.webm"),
        stopper=lambda: True,
        extractor=lambda webm: picture,
    )
    with ScreenCastSession(shell=shell) as session:
        assert session.node_id == 1
        assert grab_desktop_frame(session=session).size == picture.size


def test_start_screencast_injected_bus():
    import sys
    import types

    calls = []

    class Iface:
        def __init__(self, obj, name):
            pass

        def StopScreencast(self):
            calls.append("stop")
            return True

        def Screencast(self, dest, options):
            calls.append(("start", dest, dict(options)))
            return True, dest + ".used"

    fake = types.ModuleType("dbus")

    class UInt32(int):
        pass

    class Bus:
        def get_object(self, name, path):
            return path

    fake.UInt32 = UInt32
    fake.Interface = Iface
    fake.SessionBus = Bus
    sys.modules["dbus"] = fake
    try:
        used = start_screencast(Path("/tmp/cast.webm"), bus=Bus(), framerate=9)
        assert used == Path("/tmp/cast.used")
        assert calls[-1][1] == "/tmp/cast"
        assert "stop" in calls
        assert calls[-1][0] == "start"
        assert stop_screencast(bus=Bus()) is True
    finally:
        sys.modules.pop("dbus", None)


def test_start_screencast_refuses():
    import sys
    import types

    class Iface:
        def __init__(self, obj, name):
            pass

        def StopScreencast(self):
            return False

        def Screencast(self, dest, options):
            return False, dest

    fake = types.ModuleType("dbus")
    class Bus:
        def get_object(self, name, path):
            return path

    fake.UInt32 = lambda n: n
    fake.Interface = Iface
    sys.modules["dbus"] = fake
    try:
        with pytest.raises(RuntimeError, match="refused"):
            start_screencast(Path("/tmp/cast.webm"), bus=Bus())
    finally:
        sys.modules.pop("dbus", None)


def test_snapshot_frame_reads_png(tmp_path: Path):
    painted = _rgb((40, 90, 40), (48, 32))
    out = tmp_path / "snap.png"
    painted.save(out)

    class Iface:
        def Screencast(self, dest, options):
            assert "pngenc" in options["pipeline"]
            return True, str(out)

    slept = []
    image = snapshot_frame(tmp_path / "snap.png", iface=Iface(), sleeper=slept.append, wait=0.2)
    assert slept == [0.2]
    assert image.size == (48, 32)


def test_snapshot_frame_refuses():
    class Iface:
        def Screencast(self, dest, options):
            return False, dest

    with pytest.raises(RuntimeError, match="snapshot refused"):
        snapshot_frame(iface=Iface(), sleeper=lambda _t: None, wait=0)
