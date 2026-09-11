#!/usr/bin/env python3
"""Live open-loop: strike-zone → DN-VNC legs → frets on Midtempo Easy.

Default ``--oracle`` uses ChartEye for WHEN (chart near-bin → DN-VNC → uinput).
That isolates the fly→fret half from Screencast/eye lag. Pass ``--pixels`` to
drive from the live trapezoid eye instead (ThreadedEye + Mutter BGRx appsink by
default; ``--snapshot-eye`` for legacy PNG snapshots).

Only one launcher may run at a time (``/tmp/flyhero-play.lock``). Soft-stop
Clone Hero on boot; never mid-song killalls from this tool.

  PYTHONPATH=src python3 tools/play_prosthesis.py --boot-midtempo --pixels \\
      --out ~/fly-hero-runs/prosthesis-pixels-1
"""

from __future__ import annotations

import argparse
import fcntl
import os
import sys
import time
from pathlib import Path

for _var in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS"):
    os.environ.setdefault(_var, "2")

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

os.environ.setdefault("DISPLAY", ":0")
os.environ.setdefault("WAYLAND_DISPLAY", "wayland-0")
RUNTIME = os.environ.get("XDG_RUNTIME_DIR", "/run/user/1000")
os.environ.setdefault("XDG_RUNTIME_DIR", RUNTIME)
os.environ.setdefault("PIPEWIRE_RUNTIME_DIR", RUNTIME)
os.environ.setdefault("DBUS_SESSION_BUS_ADDRESS", f"unix:path={RUNTIME}/bus")
os.environ.setdefault("YDOTOOL_SOCKET", "/tmp/.ydotool_socket")
if "XAUTHORITY" not in os.environ:
    auths = sorted(Path(RUNTIME).glob(".mutter-Xwaylandauth.*"))
    if auths:
        os.environ["XAUTHORITY"] = str(auths[-1])

from flyhero.chart import load_chart, pick_track  # noqa: E402
from flyhero.chart_eye import ChartEye  # noqa: E402
from flyhero.guitar import GuitarMap  # noqa: E402
from flyhero.launch import clonehero_running  # noqa: E402
from flyhero.menu import focus_clonehero  # noqa: E402
from flyhero.prosthesis import LegProsthesis, ProsthesisPlayer  # noqa: E402
from flyhero.events import EventWriter  # noqa: E402
from flyhero.scorestats import read_scorestats  # noqa: E402
from flyhero.types import Action  # noqa: E402
from flyhero.uinput_hands import DeviceHands, UinputMenu, open_uinput  # noqa: E402

LOCK_PATH = Path("/tmp/flyhero-play.lock")


def _acquire_lock() -> object:
    """Exclusive flock — overlapping launchers were killing each other's CH."""
    handle = open(LOCK_PATH, "a+", encoding="utf-8")
    try:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        handle.close()
        print(
            f"ABORT: another flyhero play holds {LOCK_PATH} — one run at a time",
            flush=True,
        )
        raise SystemExit(4) from None
    handle.seek(0)
    handle.truncate()
    handle.write(f"pid={os.getpid()} started={time.time():.0f}\n")
    handle.flush()
    return handle


def _wait_score(stamp, *, timeout: float):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        row = read_scorestats()
        if row is not None and (stamp is None or row.timestamp != stamp):
            return row
        time.sleep(0.3)
    return None


def _finish(args, device, game, actions, strums, *, mode: str, near_hot: int = 0) -> int:
    events: EventWriter | None = getattr(args, "_events", None)
    if game is not None:
        print(
            f"GAME {game.notes_hit}/{game.total_notes} ({game.accuracy:.1%}) "
            f"streak={game.max_streak} overstrums={game.excess_hits} "
            f"ticks={actions} strum_ticks={strums} near_hot={near_hot}",
            flush=True,
        )
        (args.out / "result.txt").write_text(
            f"hits={game.notes_hit} notes={game.total_notes} acc={game.accuracy:.4f} "
            f"overstrums={game.excess_hits} streak={game.max_streak} mode={mode} "
            f"near_hot={near_hot}\n",
            encoding="utf-8",
        )
        if events is not None:
            events.song_end()
            events.score(
                hits=game.notes_hit,
                notes=game.total_notes,
                score=game.score,
                max_streak=game.max_streak,
                accuracy=game.accuracy,
            )
    else:
        print(
            f"GAME (no scorestats) ticks={actions} strum_ticks={strums} near_hot={near_hot}",
            flush=True,
        )
        if events is not None:
            events.song_end()
    if hasattr(device, "close"):
        device.close()
    return 0 if game is not None and game.notes_hit > 0 else 1


def _ch_alive() -> bool:
    return clonehero_running()


def main() -> int:
    lock = _acquire_lock()
    try:
        return _main_locked()
    finally:
        try:
            fcntl.flock(lock.fileno(), fcntl.LOCK_UN)
        finally:
            lock.close()


def _main_locked() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "chart",
        type=Path,
        nargs="?",
        default=Path.home() / ".clonehero/Songs/Fly Hero/Fly Hero Midtempo/notes.chart",
    )
    parser.add_argument("--track", default="EasySingle")
    parser.add_argument("--boot-midtempo", action="store_true")
    parser.add_argument(
        "--reuse-clonehero",
        action="store_true",
        help="if Clone Hero is already running, do not stop/restart it",
    )
    parser.add_argument("--query", default="fly")
    parser.add_argument("--depth", type=int, default=8)
    parser.add_argument("--step", type=float, default=0.02)
    parser.add_argument("--look-ahead", type=float, default=1.5)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--countdown", type=float, default=2.0)
    parser.add_argument(
        "--chart-offset",
        type=float,
        default=0.0,
        help="oracle only: add to wall chart_t (negative = play chart earlier)",
    )
    parser.add_argument("--near-threshold", type=float, default=0.5)
    parser.add_argument("--twitch-threshold", type=float, default=0.25)
    parser.add_argument("--amplitude", type=float, default=5.0)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument(
        "--pixels",
        action="store_true",
        help="live trapezoid eye WHEN (needs Screencast); default is ChartEye oracle",
    )
    parser.add_argument(
        "--pixel-frets-oracle-when",
        action="store_true",
        help="diagnostic: pixel frets + ChartEye WHEN (song clock from highway start)",
    )
    parser.add_argument(
        "--chart-under-pixel-boot",
        action="store_true",
        help="diagnostic: Ready-first boot + ChartEye frets/WHEN (no pixel actions)",
    )
    parser.add_argument(
        "--chart-frets-pixel-when",
        action="store_true",
        help="diagnostic: ChartEye frets + pixel scheduled WHEN",
    )
    parser.add_argument(
        "--snapshot-eye",
        action="store_true",
        help="legacy fast PNG snapshots (fallback; default is BGRx appsink)",
    )
    parser.add_argument(
        "--appsink-eye",
        action="store_true",
        help="long-lived Mutter BGRx appsink (default for --pixels)",
    )
    parser.add_argument(
        "--cast-eye",
        action="store_true",
        help="rolling Shell.Screencast webm eye (often stale tips; diagnostic)",
    )
    parser.add_argument(
        "--fullhd-snapshot",
        action="store_true",
        help="1080p snapshot pipeline instead of fast 640×360",
    )
    parser.add_argument(
        "--viz",
        action="store_true",
        default=True,
        help="side-panel DN-VNC node firing viz (default on for --pixels)",
    )
    parser.add_argument(
        "--no-viz",
        action="store_true",
        help="disable the side-panel node firing viz",
    )
    parser.add_argument(
        "--sec-per-bin",
        type=float,
        default=0.0,
        help="if >0, wait far*sec_per_bin − when_lead + when_lag; if 0 use fixed when_lag only",
    )
    parser.add_argument(
        "--when-lead",
        type=float,
        default=0.05,
        help="subtract from far*sec_per_bin when --sec-per-bin > 0",
    )
    parser.add_argument(
        "--when-lag",
        type=float,
        default=0.06,
        help="fixed defer after arm (default 0.06 — appsink pixels-75 36/39; PNG ok near 0.08)",
    )
    parser.add_argument(
        "--strum-farness",
        type=int,
        default=4,
        help="arm WHEN when nearest gem farness <= this (default 4)",
    )
    parser.add_argument(
        "--events",
        type=Path,
        default=None,
        help="append JSONL gameplay events for Fly Cast (song/fret/strum/score)",
    )
    args = parser.parse_args()
    if args.no_viz:
        args.viz = False
    args._events = EventWriter(args.events)

    text = args.chart.read_text(encoding="utf-8")
    track = pick_track(text, args.track)
    chart = load_chart(args.chart, track=track)
    args.out.mkdir(parents=True, exist_ok=True)
    mode = "pixels" if args.pixels else "oracle"
    print(
        f"prosthesis live: notes={len(chart.notes)} track={track} mode={mode} out={args.out}",
        flush=True,
    )

    mapping = GuitarMap.clone_hero_keyboard()
    device = open_uinput(mapping, menu=True)
    menu = UinputMenu(device)
    hands = DeviceHands(device, mapping)

    if args.boot_midtempo:
        from flyhero.launch import game_argv, start_clonehero, stop_clonehero
        from flyhero.session import join_guest_blind, load_midtempo_blind

        if args.reuse_clonehero and _ch_alive():
            print("boot: reusing running Clone Hero (no stop)", flush=True)
            focus_clonehero()
            hands.release_all()
        else:
            print("boot: soft-stop Clone Hero, start with uinput open", flush=True)
            stop_clonehero()
            time.sleep(0.5)
            start_clonehero(game_argv())
            # Config splash swallows early keys — settle longer than 6s.
            time.sleep(8.0)
            focus_clonehero()
            join_guest_blind(menu.tap, time.sleep, pause=1.2)
            print("boot: Guest joined", flush=True)
            hands.release_all()

        # Known-good song walk on uinput only. Vision menus after cast were
        # what stuck on songs / lied about highway (Remote Desktop + empty keys).
        focus_clonehero()
        if args.pixels:
            # Raise the appsink eye BEFORE Ready so Mutter ScreenCast / Remote
            # Desktop focus loss does not eject us from the Ready screen.
            from flyhero.pipewire import ScreenCastSession
            from flyhero.shellcast import QuietBanners, clear_remote_desktop, stop_screencast

            stop_screencast()
            early_banners = QuietBanners()
            early_banners.__enter__()
            early_cast = ScreenCastSession(backend="appsink")
            early_cast.start()
            clear_remote_desktop(tries=8)
            time.sleep(0.5)
            clear_remote_desktop(tries=4, share_only=True)
            focus_clonehero()
            args._early_appsink = (early_banners, early_cast)
            load_midtempo_blind(
                menu.tap, time.sleep, query=args.query, pause=0.9, start_song=False
            )
            print("boot: Midtempo Easy Ready (eye already live)", flush=True)
        else:
            load_midtempo_blind(
                menu.tap, time.sleep, query=args.query, pause=0.9, start_song=True
            )
            print("boot: Midtempo Easy started (blind)", flush=True)
            focus_clonehero()
            for _ in range(2):
                menu.tap("a")
                time.sleep(0.35)
        hands.release_all()

    if args.pixel_frets_oracle_when or getattr(args,"chart_under_pixel_boot",False) or getattr(args,"chart_frets_pixel_when",False):
        args.pixels = True
    if args.pixels:
        return _play_pixels(args, chart, menu, hands, device)

    eye = ChartEye(chart, look_ahead=args.look_ahead, depth=args.depth)
    prosthesis = LegProsthesis.create(
        seed=args.seed,
        near_threshold=args.near_threshold,
        twitch_threshold=args.twitch_threshold,
        amplitude=args.amplitude,
    )
    player = ProsthesisPlayer(eye, prosthesis, hands)
    player.reset()
    hands.release_all()
    before = read_scorestats()
    stamp = before.timestamp if before else None
    print(
        f"playing oracle prosthesis (countdown={args.countdown}s, "
        f"offset={args.chart_offset}s, song={chart.duration_seconds:.1f}s)",
        flush=True,
    )
    args._events.song_start(song=str(args.chart), track=args.track)
    started = time.monotonic()
    end = args.countdown + chart.duration_seconds + 1.5
    actions = 0
    strums = 0
    near_hot = 0
    hw_ticks = 0
    while time.monotonic() - started < end:
        if not _ch_alive():
            print("ABORT: clonehero process gone mid-play", flush=True)
            break
        elapsed = time.monotonic() - started
        chart_t = elapsed - args.countdown + args.chart_offset
        if actions > 0 and actions % 100 == 0:
            focus_clonehero()
        if chart_t < 0:
            hands.apply(Action.idle())
        else:
            frame = eye.see(chart_t)
            if any(float(frame.cells[i][0]) >= args.near_threshold for i in range(5)):
                near_hot += 1
            action = player.tick(chart_t)
            args._events.action_edges(tuple(action.frets), bool(action.strum))
            if action.strum:
                strums += 1
        actions += 1
        target = started + actions * args.step
        delay = target - time.monotonic()
        if delay > 0:
            time.sleep(delay)

    game = _wait_score(stamp, timeout=20.0)
    return _finish(args, device, game, actions, strums, mode=mode, near_hot=near_hot)


def _play_pixels(args, chart, menu, hands, device) -> int:
    from flyhero.capture import grab_clonehero
    from flyhero.detect import HighwayTimeout, is_highway, is_paused
    from flyhero.loader import classify
    from flyhero.pixel_eye import ThreadedEye, WindowCastEye
    from flyhero.pipewire import ScreenCastSession
    from flyhero.shellcast import (
        QuietBanners,
        clear_remote_desktop,
        remote_desktop_open,
        snapshot_frame,
        stop_screencast,
    )
    from flyhero.types import Action, FeatureFrame

    class SnapshotEye:
        """Legacy one-shot PNG snapshots. Prefer WindowCastEye (rolling cast)."""

        def __init__(self, *, depth: int, scale: float = 0.5, wait: float = 0.12) -> None:
            from flyhero.pixel import TrapezoidRoi

            self.depth = depth
            self.scale = scale
            self.wait = wait
            self.roi = TrapezoidRoi()
            self.last_image = None
            self.session = None

        def grab(self):
            from PIL import Image

            if remote_desktop_open():
                clear_remote_desktop(tries=2, share_only=True)
            last_exc: Exception | None = None
            for attempt in range(4):
                try:
                    desktop = snapshot_frame(wait=self.wait)
                    break
                except RuntimeError as exc:
                    last_exc = exc
                    time.sleep(0.15 + 0.1 * attempt)
            else:
                raise RuntimeError(f"snapshot failed after retries: {last_exc}") from last_exc
            image = grab_clonehero(frame_grabber=lambda: desktop)
            if self.scale != 1.0:
                size = (
                    max(8, int(image.width * self.scale)),
                    max(8, int(image.height * self.scale)),
                )
                image = image.resize(size, Image.Resampling.BOX)
            self.last_image = image
            return image

        def see_image(self, image, t_seconds: float) -> FeatureFrame:
            from flyhero.pixel import decode_trapezoid

            return decode_trapezoid(
                image, depth=self.depth, t_seconds=t_seconds, roi=self.roi
            )

        def see(self, t_seconds: float) -> FeatureFrame:
            return self.see_image(self.grab(), t_seconds)

    banners = QuietBanners()
    banners.__enter__()
    stop_screencast()
    clear_remote_desktop(tries=4)
    cast: ScreenCastSession | None = None
    from flyhero.shellcast import SNAPSHOT_PIPELINE, SNAPSHOT_PIPELINE_FAST

    use_snapshot = bool(
        getattr(args, "snapshot_eye", False) or getattr(args, "fullhd_snapshot", False)
    )
    use_cast = bool(getattr(args, "cast_eye", False))
    early = getattr(args, "_early_appsink", None)

    if use_cast:
        print("pixels: rolling Shell.Screencast eye (WindowCastEye)", flush=True)
        cast = ScreenCastSession(backend="shell")
        cast.start()
        clear_remote_desktop(tries=6)
        window = WindowCastEye(cast, depth=args.depth, scale=0.45)
    elif use_snapshot:
        pipe = SNAPSHOT_PIPELINE if getattr(args, "fullhd_snapshot", False) else SNAPSHOT_PIPELINE_FAST
        label = "fullhd" if pipe is SNAPSHOT_PIPELINE else "fast640"
        print(f"pixels: {label} PNG snapshot eye (QuietBanners fallback)", flush=True)

        class FastSnapshotEye(SnapshotEye):
            def __init__(self, **kw):
                super().__init__(**kw)
                self.pipeline = pipe

            def grab(self):
                from PIL import Image

                if remote_desktop_open():
                    clear_remote_desktop(tries=2, share_only=True)
                last_exc: Exception | None = None
                for attempt in range(4):
                    try:
                        desktop = snapshot_frame(wait=self.wait, pipeline=self.pipeline)
                        break
                    except RuntimeError as exc:
                        last_exc = exc
                        time.sleep(0.1 + 0.05 * attempt)
                else:
                    raise RuntimeError(f"snapshot failed after retries: {last_exc}") from last_exc
                image = grab_clonehero(frame_grabber=lambda: desktop)
                if self.scale != 1.0:
                    size = (
                        max(8, int(image.width * self.scale)),
                        max(8, int(image.height * self.scale)),
                    )
                    image = image.resize(size, Image.Resampling.BOX)
                self.last_image = image
                return image

        window = FastSnapshotEye(depth=args.depth, wait=0.0, scale=1.0)
    elif early is not None:
        early_banners, early_cast = early
        # Replace the temporary banners context with the early one.
        try:
            banners.__exit__(None, None, None)
        except Exception:
            pass
        banners = early_banners
        cast = early_cast
        print("pixels: reusing early Mutter BGRx appsink eye", flush=True)
        clear_remote_desktop(tries=4, share_only=True)
        focus_clonehero()
        # scale 0.5 BOX: full-HD decode is ~226ms (~4 Hz) and starves WHEN;
        # half-res keeps gems and lands ~50ms decode (appsink grab still ~30 Hz).
        window = WindowCastEye(cast, depth=args.depth, scale=0.5)
        args._early_appsink = None
    else:
        print("pixels: Mutter BGRx appsink eye (WindowCastEye)", flush=True)
        cast = ScreenCastSession(backend="appsink")
        cast.start()
        # Mutter ScreenCast can pop Remote Desktop / steal focus off Ready.
        clear_remote_desktop(tries=8)
        time.sleep(0.6)
        clear_remote_desktop(tries=4, share_only=True)
        focus_clonehero()
        window = WindowCastEye(cast, depth=args.depth, scale=0.5)

    def _cleanup_eye() -> None:
        if cast is not None:
            try:
                cast.close()
            except Exception:
                pass
        try:
            banners.__exit__(None, None, None)
        except Exception:
            pass

    def _grab():
        focus_clonehero()
        return window.grab()

    def _press(name: str) -> None:
        focus_clonehero()
        menu.tap(name)

    for _ in range(10):
        frame = _grab()
        if is_paused(frame):
            _press("a")
            time.sleep(0.4)
            print("pixels: resumed after cast pause", flush=True)
        else:
            break

    frame = _grab()
    label = classify(frame)
    print(f"pixels: post-cast screen={label}", flush=True)

    # Appsink start often dumps us back to the song list. Re-walk blind to Ready.
    if label in {"songs", "songs_search", "songs_pick", "main", "title", "profile"}:
        from flyhero.session import load_midtempo_blind

        print("pixels: re-blind Midtempo Ready after cast focus loss", flush=True)
        focus_clonehero()
        hands.release_all()
        load_midtempo_blind(
            menu.tap, time.sleep, query=args.query, pause=0.9, start_song=False
        )
        clear_remote_desktop(tries=4, share_only=True)
        focus_clonehero()
        frame = _grab()
        print(f"pixels: after re-blind screen={classify(frame)}", flush=True)

    # Boot left us on Ready (start_song=False). Always press start — Ready's
    # highway preview classifies as highway and would skip the song.
    print("pixels: confirm Ready → start song", flush=True)
    for _ in range(6):
        _press("a")
        time.sleep(0.45)
        frame = _grab()
        if is_paused(frame):
            _press("a")
            time.sleep(0.35)
            frame = _grab()
        if is_highway(frame) and classify(frame) == "highway":
            break
    print(f"pixels: after start screen={classify(frame)}", flush=True)

    if not is_highway(frame):
        from flyhero.loader import LoaderStuck, LoaderState, UnknownScreen, load_until_highway

        print("pixels: vision recovery loader", flush=True)
        try:
            walk = LoaderState()
            walk.passed.update(
                {"title", "profile", "main", "songs", "songs_search", "songs_pick"}
            )
            frame = load_until_highway(
                _grab,
                _press,
                query=args.query,
                settle=0.45,
                sleeper=time.sleep,
                max_steps=40,
                stuck_limit=5,
                state=walk,
            )
        except (LoaderStuck, UnknownScreen, HighwayTimeout) as exc:
            shot = args.out / "boot_stuck.png"
            if window.last_image is not None:
                window.last_image.save(shot)
            print(f"pixels: boot failed: {exc} ({shot})", flush=True)
            _cleanup_eye()
            if hasattr(device, "close"):
                device.close()
            return 2
        print(f"pixels: recovery done screen={classify(frame)}", flush=True)

    ok = False
    for _ in range(40):
        if not _ch_alive():
            print("ABORT: clonehero gone before highway", flush=True)
            break
        frame = _grab()
        if is_paused(frame):
            _press("a")
            time.sleep(0.35)
            continue
        if is_highway(frame):
            ok = True
            break
        time.sleep(0.1)
    if not ok:
        shot = args.out / "no_highway.png"
        if window.last_image is not None:
            window.last_image.save(shot)
        print(f"pixels: highway never confirmed ({shot})", flush=True)
        _cleanup_eye()
        if hasattr(device, "close"):
            device.close()
        return 1
    print("pixels: highway confirmed — starting prosthesis", flush=True)
    frame.save(args.out / "highway_start.png")
    args._events.song_start(song=str(args.chart), track=args.track)

    before = read_scorestats()
    stamp = before.timestamp if before else None
    chart_eye = ChartEye(chart, look_ahead=args.look_ahead, depth=args.depth)
    use_chart_actions = bool(getattr(args, "chart_under_pixel_boot", False))
    chart_frets_pixel_when = bool(getattr(args, "chart_frets_pixel_when", False))
    prosthesis = LegProsthesis.create(
        seed=args.seed,
        near_threshold=args.near_threshold,
        twitch_threshold=args.twitch_threshold,
        amplitude=args.amplitude,
        strum_farness=0 if chart_frets_pixel_when else 4,
    )
    threaded = ThreadedEye(window, depth=args.depth).start()
    prosthesis.reset()
    viz = None
    if getattr(args, "viz", False):
        try:
            from flyhero.node_viz import NodeFiringViz

            viz = NodeFiringViz(
                prosthesis.reservoir.size,
                prosthesis.legs,
                title="Fly Hero — node firing",
            )
            viz.show()
            print(
                f"viz: side panel open (legs={prosthesis.legs})",
                flush=True,
            )
        except Exception as exc:  # noqa: BLE001
            print(f"viz: unavailable ({exc})", flush=True)
            viz = None
    hands.release_all()
    warm = time.monotonic() + 0.25
    while time.monotonic() < warm:
        time.sleep(0.05)
    label = (
        "chart-under-pixel-boot"
        if use_chart_actions
        else ("chart-frets+pixel-WHEN" if chart_frets_pixel_when else "pixel scheduled+lag")
    )
    print(
        f"playing pixels prosthesis (ThreadedEye, song≈{chart.duration_seconds:.1f}s, {label}, "
        f"sec_per_bin={args.sec_per_bin:.3f} when_lead={args.when_lead:.3f} "
        f"when_lag={args.when_lag:.3f} strum_far<={args.strum_farness})",
        flush=True,
    )
    started = time.monotonic()
    end = chart.duration_seconds + 2.0
    actions = 0
    strums = 0
    near_hot = 0
    hw_ticks = 0
    last_eye_frames = -1
    suppress_until = 0.0
    pending_strum_at: float | None = None
    pending_frets: tuple[bool, ...] | None = None
    pending_arm_far = -1
    sec_per_bin = args.look_ahead / max(args.depth, 1)
    diag = args.out / "near_diag.tsv"
    diag.write_text("t\tmode\tlane\tfar\tstrum\n", encoding="utf-8")
    (args.out / "strum_diag.tsv").write_text(
        "t\tlane_now\tfar_now\tfar_arm\tfrets\n", encoding="utf-8"
    )
    while time.monotonic() - started < end:
        if not _ch_alive():
            print("ABORT: clonehero process gone mid-play", flush=True)
            break
        shot = threaded.latest_image or window.last_image
        if shot is not None and is_paused(shot):
            hands.release_all()
            focus_clonehero()
            menu.tap("a")
            time.sleep(0.35)
            hands.release_all()
            continue
        if shot is not None and not is_highway(shot):
            screen = classify(shot)
            if screen in {"results", "songs", "main", "title", "profile", "settings"}:
                hands.release_all()
                time.sleep(0.02)
                continue
        else:
            hw_ticks += 1
        wall = time.monotonic()
        t_now = wall - started
        pix = threaded.see(t_now)
        cframe = chart_eye.see(t_now)
        fresh_eye = threaded.frames != last_eye_frames
        last_eye_frames = threaded.frames
        best_far = None
        best_lane = None
        for lane in range(5):
            for d in range(min(5, pix.depth)):
                if float(pix.cells[lane][d]) >= args.near_threshold:
                    if best_far is None or d < best_far:
                        best_far = d
                        best_lane = lane
                    break
        if best_lane is not None:
            near_hot += 1
        if use_chart_actions:
            action = prosthesis.tick(cframe)
            if action.strum and wall < suppress_until:
                action = Action.from_frets(action.frets, False)
            if action.strum:
                suppress_until = wall + 0.05
        elif chart_frets_pixel_when:
            # Frets from chart near/approach; WHEN from pixel schedule.
            chart_lane = None
            for lane in range(5):
                if any(float(cframe.cells[lane][d]) >= args.near_threshold for d in range(cframe.depth)):
                    chart_lane = lane
                    break
            frets = (
                tuple(i == chart_lane for i in range(5))
                if chart_lane is not None
                else (False,) * 5
            )
            # Pixel WHEN: first sight of a gem schedules a short delay from farness
            # using ChartEye bin time; also fire immediately if already near (far<=1).
            strum = False
            if chart_lane is not None and wall >= suppress_until:
                if fresh_eye and best_far is not None and best_far <= 1:
                    strum = True
                elif fresh_eye and best_far is not None:
                    eta = wall + best_far * sec_per_bin - 0.05
                    if pending_strum_at is None or eta < pending_strum_at:
                        pending_strum_at = eta
            if (
                pending_strum_at is not None
                and wall >= pending_strum_at
                and chart_lane is not None
                and wall >= suppress_until
            ):
                strum = True
                pending_strum_at = None
            if strum:
                suppress_until = wall + 0.90
            action = Action.from_frets(frets, strum)
        else:
            lit = sum(
                1
                for lane in range(5)
                if any(
                    float(pix.cells[lane][d]) >= args.near_threshold
                    for d in range(min(5, pix.depth))
                )
            )
            lane = None if lit >= 4 else best_lane
            frets = (
                tuple(i == lane for i in range(5)) if lane is not None else (False,) * 5
            )
            # Queue (chord, t_hit). Hold armed frets until the strum.
            # PNG eye (~7 Hz) first-saw gems already near → fixed when_lag worked
            # (pixels-58). Appsink (~30 Hz) sees gems early → need far×sec_per_bin
            # with coast (pull eta earlier on closer re-sight) or strike-only.
            strum = False
            far_lim = int(args.strum_farness)
            spb = float(args.sec_per_bin)
            lead = float(args.when_lead)
            extra = float(args.when_lag)

            def _eta(far: int) -> float:
                if spb > 0:
                    delay = max(0.0, far * spb - lead) + max(0.0, extra)
                    return wall + delay
                # Fixed-lag mode. when_lead pulls fire earlier (appsink was
                # ~300ms late vs chart on Midtempo — frets from the *next* gem).
                delay = max(0.0, extra) - max(0.0, lead)
                return wall + delay

            if (
                fresh_eye
                and lane is not None
                and best_far is not None
                and best_far <= far_lim
                and wall >= suppress_until
                and any(frets)
            ):
                eta = _eta(int(best_far))
                if pending_strum_at is None or eta < pending_strum_at:
                    pending_strum_at = eta
                    pending_frets = frets
                    pending_arm_far = int(best_far)
            # Hold armed frets while waiting to strum.
            if pending_strum_at is not None and pending_frets is not None:
                frets = pending_frets
            if (
                pending_strum_at is not None
                and wall >= pending_strum_at
                and wall >= suppress_until
            ):
                if pending_frets is not None and any(pending_frets):
                    frets = pending_frets
                    strum = True
                    with (args.out / "strum_diag.tsv").open("a", encoding="utf-8") as sf:
                        sf.write(
                            f"{t_now:.3f}\t{best_lane if best_lane is not None else -1}\t"
                            f"{best_far if best_far is not None else -1}\t"
                            f"{pending_arm_far}\t{''.join('1' if f else '0' for f in frets)}\n"
                        )
                pending_strum_at = None
                pending_frets = None
                pending_arm_far = -1
            if strum:
                # Midtempo Easy spacing is ~1s; keep short so we don't eat the next.
                suppress_until = wall + 0.28
            action = Action.from_frets(frets, strum)
        # Reservoir always steps for the side-panel viz; frets/WHEN above win.
        if use_chart_actions:
            drive = prosthesis.drive_from_frame(cframe)
            state = prosthesis.reservoir.state
        else:
            drive = prosthesis.drive_from_frame(pix)
            state = prosthesis.reservoir.step(drive)
        if viz is not None:
            viz.update(state, drive=drive)
            if actions % 5 == 0:
                viz.pump()
            if actions % 250 == 1:
                try:
                    viz.render().save(args.out / f"viz_{actions:04d}.png")
                except Exception:
                    pass
        hands.apply(action)
        args._events.action_edges(tuple(action.frets), bool(action.strum))
        actions += 1
        if action.strum:
            strums += 1
        if actions % 50 == 1:
            diag.write_text(
                diag.read_text(encoding="utf-8")
                + f"{t_now:.2f}\t{label}\t"
                + f"{best_lane if best_lane is not None else -1}\t"
                + f"{best_far if best_far is not None else -1}\t"
                + f"{int(action.strum)}\n",
                encoding="utf-8",
            )
            if shot is not None and actions % 250 == 1:
                shot.save(args.out / f"frame_{actions:04d}.png")
        target = started + actions * args.step
        delay = target - time.monotonic()
        if delay > 0:
            time.sleep(delay)
    game = _wait_score(stamp, timeout=25.0)
    final = threaded.latest_image or window.last_image
    if final is not None:
        final.save(args.out / "results.png")
    if viz is not None:
        try:
            viz.render().save(args.out / "viz_final.png")
        except Exception:
            pass
        viz.close()
    rolls = 0
    if cast is not None and getattr(cast, "_shell", None) is not None:
        rolls = int(getattr(cast._shell, "rolls", 0) or 0)
    (args.out / "eye.txt").write_text(
        f"frames={threaded.frames} errors={threaded.errors} stale={threaded.stale} "
        f"near_hot={near_hot} hw_ticks={hw_ticks} rolls={rolls}\n",
        encoding="utf-8",
    )
    threaded.close()
    _cleanup_eye()
    return _finish(args, device, game, actions, strums, mode="pixels", near_hot=near_hot)


if __name__ == "__main__":
    raise SystemExit(main())
