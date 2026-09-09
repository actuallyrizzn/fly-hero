"""GNOME Shell.Screencast — the live fair eye on ngram.

Mutter ScreenCast + gst-launch pipewiresrc negotiates YUY2 1280×720 and
scrambles the picture. The same compositor’s Screencast service writes a
clean 1920×1080 VP8 file. We keep that recording open and pull the last
frame with ffmpeg.
"""

from __future__ import annotations

import subprocess
import tempfile
import time
from collections.abc import Callable
from pathlib import Path

from PIL import Image

from flyhero.visibility import require_visible

SHELL_NAME = "org.gnome.Shell.Screencast"
SHELL_PATH = "/org/gnome/Shell/Screencast"
SHELL_IFACE = "org.gnome.Shell.Screencast"
DEFAULT_FRAMERATE = 15
SNAPSHOT_PIPELINE = (
    "videoconvert chroma-mode=none dither=none matrix-mode=output-only "
    "! pngenc snapshot=true"
)

FfmpegRunner = Callable[..., subprocess.CompletedProcess]


def _session_bus():
    import dbus

    return dbus.SessionBus()


def _iface(bus=None):
    import dbus

    bus = bus or _session_bus()
    return dbus.Interface(bus.get_object(SHELL_NAME, SHELL_PATH), SHELL_IFACE)


def stop_screencast(bus=None) -> bool:
    """Stop a running Shell.Screencast. Missing/idle is not an error."""
    try:
        return bool(_iface(bus).StopScreencast())
    except Exception:
        return False


def start_screencast(
    dest: Path,
    *,
    bus=None,
    framerate: int = DEFAULT_FRAMERATE,
    draw_cursor: bool = False,
) -> Path:
    """Start a desktop recording. Returns the filename GNOME actually used."""
    import dbus

    dest = Path(dest)
    if dest.suffix:
        dest = dest.with_suffix("")
    dest.parent.mkdir(parents=True, exist_ok=True)
    stop_screencast(bus)
    iface = _iface(bus)
    ok, used = iface.Screencast(
        str(dest),
        {
            "framerate": dbus.UInt32(int(framerate)),
            "draw-cursor": bool(draw_cursor),
        },
    )
    if not ok:
        raise RuntimeError("GNOME Shell.Screencast refused to start")
    return Path(str(used))


def resolve_cast_file(path: Path) -> Path:
    """GNOME may append .webm / .undefined to the template we passed."""
    path = Path(path)
    candidates = [
        path,
        Path(str(path) + ".webm"),
        Path(str(path) + ".undefined"),
        path.with_suffix(".webm"),
        path.with_suffix(".png"),
    ]
    found = [p for p in candidates if p.is_file() and p.stat().st_size >= 64]
    if not found:
        raise RuntimeError("Screencast file is empty")
    return max(found, key=lambda p: p.stat().st_mtime)


def snapshot_frame(
    dest: Path | None = None,
    *,
    bus=None,
    wait: float = 1.15,
    sleeper=None,
    iface=None,
) -> Image.Image:
    """One-shot PNG via GNOME's snapshot pipeline. VP8 webm extract is flaky."""
    dest = Path(dest or Path(tempfile.gettempdir()) / "flyhero-snap")
    if dest.suffix:
        dest = dest.with_suffix("")
    dest.parent.mkdir(parents=True, exist_ok=True)
    owned = iface is None
    if owned:
        import dbus

        stop_screencast(bus)
        iface = _iface(bus)
        options = {
            "pipeline": SNAPSHOT_PIPELINE,
            "framerate": dbus.UInt32(5),
            "draw-cursor": False,
        }
    else:
        if bus is not None:
            stop_screencast(bus)
        options = {
            "pipeline": SNAPSHOT_PIPELINE,
            "framerate": 5,
            "draw-cursor": False,
        }
    ok, used = iface.Screencast(str(dest), options)
    if not ok:
        raise RuntimeError("GNOME Shell.Screencast snapshot refused")
    (sleeper or time.sleep)(wait)
    if owned or bus is not None:
        stop_screencast(bus)
    path = resolve_cast_file(Path(str(used)))
    return require_visible(Image.open(path).convert("RGB"))


def extract_frame(
    webm: Path,
    *,
    runner: FfmpegRunner | None = None,
    timeout: float = 8.0,
    sseof: float = 0.3,
) -> Image.Image:
    """Decode the last frame of a growing Screencast webm."""
    run = runner or subprocess.run
    webm = resolve_cast_file(Path(webm))
    with tempfile.TemporaryDirectory(prefix="flyhero-sc-") as tmp:
        out = Path(tmp) / "frame.png"
        command = [
            "ffmpeg",
            "-y",
            "-sseof",
            f"-{sseof}",
            "-i",
            str(webm),
            "-frames:v",
            "1",
            "-update",
            "1",
            str(out),
        ]
        try:
            completed = run(command, check=False, capture_output=True, text=True, timeout=timeout)
        except subprocess.TimeoutExpired as exc:
            raise RuntimeError("ffmpeg extract timed out") from exc
        if completed.returncode != 0 or not out.is_file() or out.stat().st_size < 32:
            err = (completed.stderr or completed.stdout or "ffmpeg failed").strip()
            raise RuntimeError(f"ffmpeg extract: {err[-400:]}")
        return require_visible(Image.open(out).convert("RGB"))


class ShellScreencast:
    """Long-lived GNOME recording. Open once, grab many frames."""

    def __init__(
        self,
        *,
        dest: Path | None = None,
        starter: Callable[..., Path] | None = None,
        stopper: Callable[..., bool] | None = None,
        extractor: Callable[..., Image.Image] | None = None,
        framerate: int = DEFAULT_FRAMERATE,
        sleeper=None,
    ) -> None:
        self.dest = dest
        self._starter = starter or start_screencast
        self._stopper = stopper or stop_screencast
        self._extractor = extractor or extract_frame
        self._sleep = sleeper or time.sleep
        self._webm: Path | None = None
        self.framerate = framerate

    def start(self) -> Path:
        # GNOME 50 rejects a file_template that already has .webm
        dest = self.dest or Path(tempfile.gettempdir()) / "flyhero-live"
        self._webm = self._starter(dest, framerate=self.framerate)
        return self._webm

    def grab(self) -> Image.Image:
        if self._webm is None:
            self.start()
        last: Exception | None = None
        for attempt in range(8):
            try:
                return self._extractor(self._webm)
            except RuntimeError as exc:
                last = exc
                self._sleep(0.25)
        raise last or RuntimeError("Screencast produced no frame")

    def close(self) -> None:
        self._webm = None
        try:
            self._stopper()
        except Exception:
            pass

    def __enter__(self) -> ShellScreencast:
        self.start()
        return self

    def __exit__(self, *exc) -> None:
        self.close()
