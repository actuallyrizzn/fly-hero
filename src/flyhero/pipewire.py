"""GNOME PipeWire capture — the live fair eye on ngram.

X11 ImageGrab of Clone Hero is black (Unity on Xwayland). kmsgrab sees the
plane but Intel CCS tiles come out as noise. GNOME already composites a clean
frame into PipeWire via Mutter ScreenCast.

CI never opens D-Bus. Inject ``bus``, ``wait_node``, and ``gst`` in tests.
"""

from __future__ import annotations

import os
import subprocess
import tempfile
from collections.abc import Callable
from pathlib import Path

from PIL import Image

from flyhero.shellcast import ShellScreencast
from flyhero.visibility import require_visible

MUTTER_NAME = "org.gnome.Mutter.ScreenCast"
MUTTER_PATH = "/org/gnome/Mutter/ScreenCast"
MUTTER_IFACE = "org.gnome.Mutter.ScreenCast"
SESSION_IFACE = "org.gnome.Mutter.ScreenCast.Session"
STREAM_IFACE = "org.gnome.Mutter.ScreenCast.Stream"
CURSOR_HIDDEN = 0
DEFAULT_CONNECTOR = "eDP-1"

GstGrabber = Callable[[int], Image.Image]
NodeWaiter = Callable[[object, str], int]


def detect_connector(sys_drm: Path | None = None) -> str:
    """Prefer the laptop panel. Fall back to the first connected connector."""
    root = sys_drm or Path("/sys/class/drm")
    if not root.is_dir():
        return DEFAULT_CONNECTOR
    connected: list[str] = []
    for entry in sorted(root.iterdir()):
        name = entry.name
        if not name.startswith("card") or "-" not in name:
            continue
        status = entry / "status"
        if not status.is_file():
            continue
        if status.read_text(encoding="utf-8").strip() != "connected":
            continue
        connector = name.split("-", 1)[1]
        if connector.startswith("eDP"):
            return connector
        connected.append(connector)
    return connected[0] if connected else DEFAULT_CONNECTOR


def grab_pipewire_node(
    node_id: int,
    *,
    runner: Callable[..., subprocess.CompletedProcess] | None = None,
    timeout: float = 12.0,
) -> Image.Image:
    """Pull one RGB frame from a PipeWire node via GStreamer."""
    if node_id <= 0:
        raise ValueError("PipeWire node id must be positive")
    run = runner or subprocess.run
    env = os.environ.copy()
    if env.get("XDG_RUNTIME_DIR") and "PIPEWIRE_RUNTIME_DIR" not in env:
        env["PIPEWIRE_RUNTIME_DIR"] = env["XDG_RUNTIME_DIR"]
    with tempfile.TemporaryDirectory(prefix="flyhero-pw-") as tmp:
        out = Path(tmp) / "frame.png"
        command = [
            "gst-launch-1.0",
            "-q",
            "pipewiresrc",
            f"target-object={node_id}",
            "keepalive-time=1000",
            "num-buffers=1",
            "!",
            "videoconvert",
            "!",
            "pngenc",
            "!",
            "filesink",
            f"location={out}",
        ]
        try:
            completed = run(
                command,
                check=False,
                capture_output=True,
                text=True,
                timeout=timeout,
                env=env,
            )
        except subprocess.TimeoutExpired as exc:
            raise RuntimeError(f"pipewiresrc node {node_id}: timed out") from exc
        if completed.returncode != 0 or not out.is_file() or out.stat().st_size < 32:
            err = (completed.stderr or completed.stdout or "gstreamer failed").strip()
            raise RuntimeError(f"pipewiresrc node {node_id}: {err}")
        return Image.open(out).convert("RGB")


def _session_bus():
    import dbus

    return dbus.SessionBus()


def mutter_open(
    *,
    connector: str | None = None,
    bus=None,
    wait_node: NodeWaiter | None = None,
) -> tuple[object, object, int]:
    """Start a monitor screencast. Returns (session, stream_path, node_id)."""
    try:
        import dbus
    except ImportError as exc:
        raise RuntimeError(
            "live capture needs python3-dbus (system). "
            "On ngram set include-system-site-packages = true in .venv/pyvenv.cfg"
        ) from exc

    connector = connector or detect_connector()
    if bus is None and wait_node is None:
        from dbus.mainloop.glib import DBusGMainLoop

        DBusGMainLoop(set_as_default=True)
    bus = bus or _session_bus()
    cast = dbus.Interface(bus.get_object(MUTTER_NAME, MUTTER_PATH), MUTTER_IFACE)
    session_path = str(cast.CreateSession({}))
    session = dbus.Interface(bus.get_object(MUTTER_NAME, session_path), SESSION_IFACE)
    stream_path = str(
        session.RecordMonitor(
            connector,
            {"cursor-mode": dbus.UInt32(CURSOR_HIDDEN)},
        )
    )
    if wait_node is not None:
        session.Start()
        node_id = int(wait_node(bus, stream_path))
    else:
        node_id = _start_and_wait_node(bus, session, stream_path)
    if node_id <= 0:
        raise RuntimeError("Mutter ScreenCast did not publish a PipeWire node")
    return session, stream_path, node_id


def _start_and_wait_node(bus, session, stream_path: str, timeout_ms: int = 5000) -> int:
    """Subscribe, Start, then block until PipeWireStreamAdded."""
    from gi.repository import GLib

    found: list[int] = []
    loop = GLib.MainLoop()

    def on_added(node_id):
        found.append(int(node_id))
        loop.quit()

    bus.add_signal_receiver(
        on_added,
        signal_name="PipeWireStreamAdded",
        dbus_interface=STREAM_IFACE,
        path=stream_path,
    )
    session.Start()
    GLib.timeout_add(timeout_ms, loop.quit)
    loop.run()
    return found[0] if found else 0


class ScreenCastSession:
    """Long-lived monitor capture. Open once, grab many frames.

    Live default is GNOME Shell.Screencast (clean 1080p). Pass ``opener`` /
    ``gst`` for the raw PipeWire path (tests, gamescope).
    """

    def __init__(
        self,
        *,
        connector: str | None = None,
        opener: Callable[..., tuple[object, object, int]] | None = None,
        gst: GstGrabber | None = None,
        shell: ShellScreencast | None = None,
        backend: str = "shell",
    ) -> None:
        self.connector = connector
        self.backend = "pipewire" if opener is not None else backend
        self._opener = opener
        self._gst = gst
        self._shell = shell
        self._session = None
        self.node_id = 0

    def start(self) -> int:
        if self.backend == "pipewire" or self._opener is not None:
            opener = self._opener or mutter_open
            session, _stream, node_id = opener(connector=self.connector)
            self._session = session
            self.node_id = int(node_id)
            return self.node_id
        self._shell = self._shell or ShellScreencast()
        self._shell.start()
        self.node_id = 1
        return self.node_id

    def grab(self) -> Image.Image:
        if self._shell is not None or (self.backend == "shell" and self._opener is None):
            if self._shell is None:
                self.start()
            return self._shell.grab()
        if self.node_id <= 0:
            self.start()
        gst = self._gst or grab_pipewire_node
        return require_visible(gst(self.node_id))

    def close(self) -> None:
        if self._shell is not None:
            self._shell.close()
            self._shell = None
        session = self._session
        self._session = None
        self.node_id = 0
        if session is None:
            return
        stop = getattr(session, "Stop", None)
        if stop is not None:
            try:
                stop()
            except Exception:
                pass

    def __enter__(self) -> ScreenCastSession:
        self.start()
        return self

    def __exit__(self, *exc) -> None:
        self.close()


def grab_desktop_frame(
    *,
    session: ScreenCastSession | None = None,
    connector: str | None = None,
) -> Image.Image:
    """One visible desktop frame. Opens a short session when none is passed."""
    if session is not None:
        return session.grab()
    with ScreenCastSession(connector=connector) as owned:
        return owned.grab()
