#!/usr/bin/env python3
"""Print (or exec) the Clone Hero command that opens a song. Not a player."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from flyhero.config import HostConfig  # noqa: E402
from flyhero.launch import DEFAULT_FIRST_SONG, load_song_argv  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Harness: load a Clone Hero song")
    parser.add_argument(
        "song",
        nargs="?",
        type=Path,
        default=DEFAULT_FIRST_SONG,
        help="song folder or notes.chart (default: Kazotsky Kick vGH)",
    )
    parser.add_argument("--exec", action="store_true", help="replace this process with Clone Hero")
    parser.add_argument("--width", type=int, default=1280)
    parser.add_argument("--height", type=int, default=720)
    parser.add_argument("--fullscreen", action="store_true")
    args = parser.parse_args()
    argv = load_song_argv(
        args.song,
        config=HostConfig(),
        width=args.width,
        height=args.height,
        fullscreen=args.fullscreen,
    )
    print(" ".join(argv))
    if args.exec:
        os.execv(argv[0], argv)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
