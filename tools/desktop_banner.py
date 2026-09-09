#!/usr/bin/env python3
"""Show harness status on the ngram desktop (Phase 0 visual route)."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from flyhero.desktop import probe  # noqa: E402


def main() -> int:
    report = probe()
    lines = [
        "Fly Hero — Phase 0 harness",
        f"display={report.display}",
        f"clonehero={report.clonehero}",
        f"uinput={report.uinput}",
        f"songs={report.songs}",
        f"ready={report.ready}",
    ]
    text = "\n".join(lines)
    print(text)
    display = report.display or ":0"
    try:
        subprocess.run(
            [
                "zenity",
                "--info",
                "--title=Fly Hero",
                "--text=" + text,
                "--timeout=20",
            ],
            check=False,
            env={**dict(**{k: v for k, v in __import__("os").environ.items()}), "DISPLAY": display},
            timeout=25,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
