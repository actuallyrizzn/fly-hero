#!/usr/bin/env python3
"""Harness entry: teach + score offline, or load a song and play on ngram."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from flyhero.session import run_offline_path  # noqa: E402


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
        help="ngram only: launch Clone Hero and play.",
    )
    args = parser.parse_args()
    if args.live:
        raise SystemExit(
            "live session is the ngram demo. Run offline first; "
            "wire --live after probe() is ready. See docs/HARNESS.md."
        )
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
