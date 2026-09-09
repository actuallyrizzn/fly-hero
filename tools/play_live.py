#!/usr/bin/env python3
"""Play one chart into a virtual guitar. Default: POC eye + /dev/uinput."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from flyhero.capture import grab_clonehero  # noqa: E402
from flyhero.chart import load_chart  # noqa: E402
from flyhero.guitar import GuitarMap  # noqa: E402
from flyhero.live import play_live  # noqa: E402
from flyhero.pixel_eye import LivePixelEye  # noqa: E402
from flyhero.pipewire import ScreenCastSession  # noqa: E402
from flyhero.uinput_hands import DeviceHands, RecordingHands, open_uinput  # noqa: E402

TRACKS = ("EasySingle", "MediumSingle", "HardSingle", "ExpertSingle")


def pick_track(path: Path, requested: str) -> str:
    text = path.read_text(encoding="utf-8")
    if requested != "auto":
        if f"[{requested}]" not in text:
            raise SystemExit(f"{path} has no [{requested}]")
        return requested
    for name in TRACKS:
        if f"[{name}]" in text:
            return name
    raise SystemExit(f"{path} has no guitar track")


def main() -> int:
    parser = argparse.ArgumentParser(description="Fly Hero live play")
    parser.add_argument("chart", type=Path, help="notes.chart")
    parser.add_argument("--track", default="auto", help="EasySingle or auto")
    parser.add_argument("--countdown", type=float, default=3.0)
    parser.add_argument("--dry-run", action="store_true", help="log keys, do not open uinput")
    parser.add_argument("--pixels", action="store_true", help="fair eye: live PipeWire frames")
    parser.add_argument(
        "--map",
        choices=("numbers", "clone-hero"),
        default="clone-hero",
        help="numbers=1-5+Down (CI). clone-hero=A S J K L + Down (stock CH)",
    )
    parser.add_argument("--look-ahead", type=float, default=1.5)
    parser.add_argument("--depth", type=int, default=8)
    parser.add_argument("--step", type=float, default=0.02)
    args = parser.parse_args()
    track = pick_track(args.chart, args.track)
    chart = load_chart(args.chart, track=track)
    mapping = GuitarMap.clone_hero_keyboard() if args.map == "clone-hero" else GuitarMap()
    print(
        f"song={chart.name} track={track} notes={len(chart.notes)} "
        f"duration={chart.duration_seconds:.2f}s map={args.map} pixels={args.pixels}"
    )
    if args.dry_run:
        class _Clock:
            def __init__(self) -> None:
                self.t = 0.0

            def now(self) -> float:
                return self.t

            def sleep(self, delay: float) -> None:
                self.t += delay

        clock = _Clock()
        hands = RecordingHands(mapping)
        play_live(
            chart,
            hands,
            look_ahead=args.look_ahead,
            depth=args.depth,
            step=args.step,
            countdown=args.countdown,
            clock=clock.now,
            sleeper=clock.sleep,
        )
        print(hands.render())
        return 0

    session = None
    eye = None
    if args.pixels:
        session = ScreenCastSession()
        session.start()
        eye = LivePixelEye(
            lambda _t: grab_clonehero(frame_grabber=session.grab),
            depth=args.depth,
        )
    device = open_uinput(mapping)
    try:
        play_live(
            chart,
            DeviceHands(device, mapping),
            eye=eye,
            look_ahead=args.look_ahead,
            depth=args.depth,
            step=args.step,
            countdown=args.countdown,
        )
    finally:
        if hasattr(device, "close"):
            device.close()
        if session is not None:
            session.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
