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
DEFAULT_FRAMERATE = 30
# Keep the live webm short: remux cost and frozen-keyframe risk both grow with size.
ROLLING_MAX_BYTES = 2_000_000
ROLLING_MAX_AGE_S = 8.0
SNAPSHOT_PIPELINE = (
    "videoconvert chroma-mode=none dither=none matrix-mode=output-only "
    "! pngenc snapshot=true"
)
# Downscaled PNG snapshot — same compositor path as full HD, ~3× faster on ngram.
# Crop must use native screen size (xdpyinfo) because xwininfo coords are full-res.
SNAPSHOT_PIPELINE_FAST = (
    "videoscale ! video/x-raw,width=640,height=360 ! "
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


class QuietBanners:
    """Hide GNOME notification banners for the life of a live session.

    One-shot ``snapshot_frame`` starts+stops Screencast every grab. Each stop
    posts ``Screencast ended unexpectedly``, which steals focus from Clone Hero.
    Prefer a long-lived ``ShellScreencast`` / ``ScreenCastSession`` *and* keep
    banners off so a final Stop cannot yank the keyboard.
    """

    SCHEMA = "org.gnome.desktop.notifications"
    KEY = "show-banners"

    def __init__(self, runner=None) -> None:
        self.runner = runner
        self._prior: str | None = None

    def _gsettings(self, *args: str) -> subprocess.CompletedProcess:
        run = self.runner or subprocess.run
        return run(
            ["gsettings", *args],
            check=False,
            capture_output=True,
            text=True,
        )

    def __enter__(self) -> QuietBanners:
        got = self._gsettings("get", self.SCHEMA, self.KEY)
        self._prior = (got.stdout or "").strip() or "true"
        self._gsettings("set", self.SCHEMA, self.KEY, "false")
        return self

    def __exit__(self, *exc) -> None:
        value = self._prior if self._prior in {"true", "false"} else "true"
        self._gsettings("set", self.SCHEMA, self.KEY, value)
        self._prior = None


def dismiss_screencast_toasts(runner=None) -> None:
    """Best-effort close of leftover Shell notification banners."""
    run = runner or subprocess.run
    # gsettings already hides new banners; this clears sticky ones if any.
    js = (
        "(() => { try {"
        " const ml = Main.panel.statusArea.dateMenu._messageList;"
        " ml._sectionList.get_children().forEach(s => {"
        "  try { s._list.get_children().forEach(n => { try { n.close(); } catch(e){} }); }"
        "  catch(e){}"
        " }); } catch(e){} return 'ok'; })()"
    )
    run(
        [
            "gdbus",
            "call",
            "--session",
            "--dest",
            "org.gnome.Shell",
            "--object-path",
            "/org/gnome/Shell",
            "--method",
            "org.gnome.Shell.Eval",
            js,
        ],
        check=False,
        capture_output=True,
        text=True,
    )


def dismiss_remote_desktop_prompt(runner=None, *, share_only: bool = False) -> bool:
    """Close GNOME Remote Desktop Share when ``xdotool`` can see it.

    Do **not** spray absolute clicks when the window id is missing — those land
    on Clone Hero and dump Ready → title (mid20–mid22). Wayland sometimes
    hides the id; callers then use ``share_only`` retries only while
    ``remote_desktop_open()`` is true, or accept a growing webm as enough.
    """
    run = runner or subprocess.run
    try:
        found = run(
            ["xdotool", "search", "--name", "Remote Desktop"],
            check=False,
            capture_output=True,
            text=True,
        )
    except FileNotFoundError:
        return False
    ids = (found.stdout or "").split()
    if not ids:
        return False
    wid = ids[0]
    run(["timeout", "1", "xdotool", "windowactivate", "--sync", wid], check=False)
    time.sleep(0.2)
    geo = run(
        ["xdotool", "getwindowgeometry", "--shell", wid],
        check=False,
        capture_output=True,
        text=True,
    )
    x = y = width = height = 0
    for line in (geo.stdout or "").splitlines():
        if line.startswith("X="):
            x = int(line.split("=", 1)[1])
        elif line.startswith("Y="):
            y = int(line.split("=", 1)[1])
        elif line.startswith("WIDTH="):
            width = int(line.split("=", 1)[1])
        elif line.startswith("HEIGHT="):
            height = int(line.split("=", 1)[1])
    if width <= 40 or height <= 40:
        return False
    if not share_only:
        # One toggle click only — repeats flip ON→OFF.
        run(
            [
                "xdotool",
                "mousemove",
                "--sync",
                str(x + width // 2),
                str(y + int(height * 0.55)),
                "click",
                "1",
            ],
            check=False,
        )
        time.sleep(0.2)
    for sx, sy in (
        (x + int(width * 0.88), y + int(height * 0.10)),
        (x + int(width * 0.84), y + int(height * 0.14)),
    ):
        run(
            ["xdotool", "mousemove", "--sync", str(sx), str(sy), "click", "1"],
            check=False,
        )
        time.sleep(0.15)
    time.sleep(0.35)
    still = run(
        ["xdotool", "search", "--name", "Remote Desktop"],
        check=False,
        capture_output=True,
        text=True,
    )
    return not (still.stdout or "").strip()




def remote_desktop_open(runner=None) -> bool:
    """True when GNOME's Remote Desktop Share dialog is on screen."""
    run = runner or subprocess.run
    try:
        found = run(
            ["xdotool", "search", "--name", "Remote Desktop"],
            check=False,
            capture_output=True,
            text=True,
        )
    except FileNotFoundError:
        return False
    return bool((found.stdout or "").strip())


def clear_remote_desktop(
    runner=None, *, tries: int = 8, pause: float = 0.4, share_only: bool = False
) -> bool:
    """Dismiss Share while the window is visible. No blind desktop clicks."""
    for i in range(tries):
        if not remote_desktop_open(runner=runner):
            return True
        dismiss_remote_desktop_prompt(runner=runner, share_only=share_only or i > 0)
        time.sleep(pause)
    return not remote_desktop_open(runner=runner)




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
    wait: float = 0.0,
    sleeper=None,
    iface=None,
    pipeline: str | None = None,
) -> Image.Image:
    """One-shot PNG via GNOME's snapshot pipeline.

    Default pipeline is ``SNAPSHOT_PIPELINE_FAST`` (640×360) — clean compositor
    pixels at ~130ms on ngram. Full-HD ``SNAPSHOT_PIPELINE`` is ~425ms.

    **Do not call this in a menu loop without QuietBanners.** Each start/stop
    posts ``Screencast ended unexpectedly``, which steals focus from Clone Hero.
    Prefer a long-lived ``ShellScreencast`` / ``ScreenCastSession`` for menus;
    for play ticks, fast snapshots under QuietBanners beat frozen webm tips.
    """
    dest = Path(dest or Path(tempfile.gettempdir()) / "flyhero-snap")
    if dest.suffix:
        dest = dest.with_suffix("")
    dest.parent.mkdir(parents=True, exist_ok=True)
    pipe = pipeline if pipeline is not None else SNAPSHOT_PIPELINE_FAST
    owned = iface is None
    if owned:
        import dbus

        stop_screencast(bus)
        iface = _iface(bus)
        options = {
            "pipeline": pipe,
            "framerate": dbus.UInt32(5),
            "draw-cursor": False,
        }
    else:
        if bus is not None:
            stop_screencast(bus)
        options = {
            "pipeline": pipe,
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
    """Decode the last frame of a growing Screencast webm.

    GNOME appends to an open VP8/webm. ``ffmpeg -sseof`` on a raw ``cp`` of that
    live file often returns the **same** first keyframe forever while the file
    keeps growing (pixels-11: 37 grabs / 1 unique). Always ``-c copy`` remux the
    snapshot first, then ``-sseof`` — remux is cheap while we keep the cast short.

    **Never** open the live path with ffmpeg for remux: that stalls GNOME's
    writer. ``cp`` a snapshot first, remux the copy, then ``-sseof``.
    """
    import shutil

    run = runner or subprocess.run
    webm = resolve_cast_file(Path(webm))
    with tempfile.TemporaryDirectory(prefix="flyhero-sc-") as tmp:
        out = Path(tmp) / "frame.png"
        snap = Path(tmp) / "snap.webm"
        fixed = Path(tmp) / "fixed.webm"
        try:
            shutil.copyfile(webm, snap)
        except OSError as exc:
            raise RuntimeError(f"screencast snapshot failed: {exc}") from exc
        if snap.stat().st_size < 64:
            raise RuntimeError("Screencast file is empty")

        remux = [
            "ffmpeg",
            "-y",
            "-err_detect",
            "ignore_err",
            "-i",
            str(snap),
            "-c",
            "copy",
            str(fixed),
        ]
        try:
            remuxed = run(remux, check=False, capture_output=True, text=True, timeout=timeout)
        except subprocess.TimeoutExpired as exc:
            raise RuntimeError("ffmpeg extract timed out") from exc
        source = (
            fixed
            if remuxed.returncode == 0 and fixed.is_file() and fixed.stat().st_size >= 64
            else snap
        )

        command = [
            "ffmpeg",
            "-y",
            "-sseof",
            f"-{sseof}",
            "-i",
            str(source),
            "-frames:v",
            "1",
            "-update",
            "1",
            str(out),
        ]
        try:
            completed = run(
                command, check=False, capture_output=True, text=True, timeout=timeout
            )
        except subprocess.TimeoutExpired as exc:
            raise RuntimeError("ffmpeg extract timed out") from exc
        if completed.returncode != 0 or not out.is_file() or out.stat().st_size < 32:
            err = (completed.stderr or completed.stdout or "ffmpeg failed").strip()
            raise RuntimeError(f"ffmpeg extract: {err[-400:]}")
        return require_visible(Image.open(out).convert("RGB"))


class ShellScreencast:
    """Long-lived GNOME recording. Open once, grab many frames.

    Rolls (stop+start) when the webm grows past ``max_bytes`` or ``max_age_s``
    so ``cp``+remux stays cheap and ``-sseof`` keeps seeing new pixels. One-shot
    ``snapshot_frame`` is slower (~0.5s) and steals focus — not the live path.
    """

    def __init__(
        self,
        *,
        dest: Path | None = None,
        starter: Callable[..., Path] | None = None,
        stopper: Callable[..., bool] | None = None,
        extractor: Callable[..., Image.Image] | None = None,
        framerate: int = DEFAULT_FRAMERATE,
        sleeper=None,
        max_bytes: int = ROLLING_MAX_BYTES,
        max_age_s: float = ROLLING_MAX_AGE_S,
    ) -> None:
        self.dest = dest
        self._starter = starter or start_screencast
        self._stopper = stopper or stop_screencast
        self._extractor = extractor or extract_frame
        self._sleep = sleeper or time.sleep
        self._webm: Path | None = None
        self.framerate = framerate
        self.max_bytes = max(64, int(max_bytes))
        self.max_age_s = max(0.2, float(max_age_s))
        self._last_digest: bytes | None = None
        self._stale_grabs = 0
        self._started_at = 0.0
        self.rolls = 0

    def start(self) -> Path:
        # GNOME 50 rejects a file_template that already has .webm
        dest = self.dest or Path(tempfile.gettempdir()) / "flyhero-live"
        self._webm = self._starter(dest, framerate=self.framerate)
        self._last_digest = None
        self._stale_grabs = 0
        self._started_at = time.monotonic()
        # Screencast start can raise the Remote Desktop Share modal.
        clear_remote_desktop()
        if self.webm_bytes() >= 64:
            clear_remote_desktop(share_only=True, tries=4)
        # Real GNOME writes a growing webm; Cancel leaves a tiny/empty file.
        # Injected starters (unit tests) skip the wait.
        if self._starter is not start_screencast:
            return self._webm
        deadline = time.monotonic() + 6.0
        saw_file = False
        while time.monotonic() < deadline:
            n = self.webm_bytes()
            if n >= 64:
                return self._webm
            if n > 0:
                saw_file = True
            else:
                for candidate in (
                    self._webm,
                    Path(str(self._webm) + ".webm"),
                    self._webm.with_suffix(".webm"),
                ):
                    if candidate.is_file():
                        saw_file = True
                        break
            self._sleep(0.2)
        if saw_file:
            raise RuntimeError("Screencast started but wrote no frames (Share cancelled?)")
        return self._webm

    def webm_bytes(self) -> int:
        """Size of the live recording, or 0 if not started / missing."""
        if self._webm is None:
            return 0
        try:
            return resolve_cast_file(self._webm).stat().st_size
        except (OSError, RuntimeError):
            for candidate in (
                self._webm,
                Path(str(self._webm) + ".webm"),
                self._webm.with_suffix(".webm"),
            ):
                try:
                    if candidate.is_file():
                        return candidate.stat().st_size
                except OSError:
                    continue
            return 0

    def needs_roll(self) -> bool:
        """True when the open recording is too big or too old for a fast grab."""
        if self._webm is None or self._started_at <= 0:
            return False
        if self.webm_bytes() >= self.max_bytes:
            return True
        return (time.monotonic() - self._started_at) >= self.max_age_s

    def maybe_roll(self) -> bool:
        """Restart the cast when size/age budgets trip. Returns True if rolled."""
        if not self.needs_roll():
            return False
        self.restart()
        self.rolls += 1
        return True

    def grab(self) -> Image.Image:
        import hashlib

        if self._webm is None:
            self.start()
        else:
            self.maybe_roll()
        last: Exception | None = None
        for attempt in range(6):
            try:
                # Vary sseof slightly so we do not keep decoding the same keyframe.
                sseof = 0.15 + 0.05 * (attempt % 4)
                if self._extractor is extract_frame:
                    image = extract_frame(self._webm, sseof=sseof)
                else:
                    image = self._extractor(self._webm)
                digest = hashlib.sha1(image.tobytes()).digest()
                if digest == self._last_digest:
                    self._stale_grabs += 1
                    # Stale tip of a growing file → force a fresh recording.
                    if self._stale_grabs >= 3:
                        self.restart()
                        self.rolls += 1
                        self._stale_grabs = 0
                        continue
                    # Return immediately — ThreadedEye skips dupes. Retrying
                    # extract here doubled grab latency for no new pixels.
                    return image
                self._last_digest = digest
                self._stale_grabs = 0
                return image
            except RuntimeError as exc:
                last = exc
                self._sleep(0.15)
                # Empty / stalled writer: roll and retry.
                try:
                    self.restart()
                    self.rolls += 1
                except Exception:
                    pass
        raise last or RuntimeError("Screencast produced no frame")

    def restart(self) -> Path:
        """Stop and start a fresh recording so grabs stay fast.

        Each ``grab`` ``cp`` + remuxes the growing webm. After a few songs the
        file is tens of MB and ThreadedEye drops to a handful of frames/episode.
        Rolling every ~1s during play keeps remux cheap and tips fresh.
        """
        self.close()
        self._sleep(0.12)
        path = self.start()
        clear_remote_desktop(share_only=True, tries=3)
        return path

    def close(self) -> None:
        self._webm = None
        self._last_digest = None
        self._started_at = 0.0
        try:
            self._stopper()
        except Exception:
            pass

    def __enter__(self) -> ShellScreencast:
        self.start()
        return self

    def __exit__(self, *exc) -> None:
        self.close()
