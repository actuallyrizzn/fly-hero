#!/usr/bin/env python3
"""Harness entry: teach + score offline, or load a song and play on ngram."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from flyhero.desktop import probe  # noqa: E402
from flyhero.guitar import GuitarMap  # noqa: E402
from flyhero.session import run_live_path, run_offline_path  # noqa: E402
from flyhero.uinput_hands import DeviceHands, RecordingHands, TeeHands, open_uinput  # noqa: E402


def _desktop_env() -> None:
    os.environ.setdefault("DISPLAY", ":0")
    os.environ.setdefault("WAYLAND_DISPLAY", "wayland-0")
    runtime = os.environ.get("XDG_RUNTIME_DIR", "/run/user/1000")
    os.environ.setdefault("XDG_RUNTIME_DIR", runtime)
    os.environ.setdefault("PIPEWIRE_RUNTIME_DIR", runtime)
    os.environ.setdefault("DBUS_SESSION_BUS_ADDRESS", f"unix:path={runtime}/bus")


def main() -> int:
    parser = argparse.ArgumentParser(description="Fly Hero harness session")
    parser.add_argument("chart", type=Path, help="notes.chart")
    parser.add_argument("--track", default="auto")
    parser.add_argument(
        "--offline",
        action="store_true",
        default=True,
        help="teach + record + score (default). No Clone Hero.",
    )
    parser.add_argument(
        "--live",
        action="store_true",
        help="ngram: walk menus to the highway, play, score.",
    )
    parser.add_argument(
        "--load-only",
        action="store_true",
        help="live load + highway wait, do not press keys.",
    )
    parser.add_argument("--countdown", type=float, default=3.0)
    args = parser.parse_args()
    if args.live or args.load_only:
        _desktop_env()
        report = probe()
        if not report.ready:
            print(
                f"desktop not ready clonehero={report.clonehero} "
                f"uinput={report.uinput} display={report.display}",
                file=sys.stderr,
            )
            return 2
        device = None
        hands = None
        if not args.load_only:
            mapping = GuitarMap.clone_hero_keyboard()
            device = open_uinput(mapping)
            hands = TeeHands(DeviceHands(device, mapping), RecordingHands(mapping))
        try:
            result = run_live_path(
                args.chart,
                track=args.track,
                countdown=args.countdown,
                play=not args.load_only,
                keep_game=True,
                hands=hands,
            )
        finally:
            if device is not None and hasattr(device, "close"):
                device.close()
        scored = result.score
        print(
            f"song={result.chart.name} track={result.track} "
            f"notes={scored.notes} hits={scored.hits} "
            f"accuracy={scored.accuracy:.3f} events={len(result.log.events)}"
        )
        if result.log.events:
            print(result.log.render())
        if args.load_only:
            return 0
        return 0 if result.log.events else 1
    result = run_offline_path(args.chart, track=args.track)
    report = result.score
    print(
        f"song={result.chart.name} track={result.track} "
        f"notes={report.notes} hits={report.hits} accuracy={report.accuracy:.3f}"
    )
    print(result.log.render())
    return 0 if report.accepted() else 1


if __name__ == "__main__":
    raise SystemExit(main())
