#!/usr/bin/env python3
"""Save one PipeWire frame of the desktop (and Clone Hero crop if the window exists)."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from flyhero.capture import grab_clonehero  # noqa: E402
from flyhero.pipewire import ScreenCastSession, detect_connector  # noqa: E402
from flyhero.visibility import is_visible, max_luma, mean_luma  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Fly Hero PipeWire frame grab")
    parser.add_argument("-o", "--output", type=Path, default=Path("/tmp/flyhero-vis/pipewire.png"))
    parser.add_argument("--connector", default=None, help="DRM connector, default: detect eDP")
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    connector = args.connector or detect_connector()
    print(f"connector={connector} backend=shell")
    with ScreenCastSession(connector=connector) as session:
        print(f"session_ready node={session.node_id}")
        image = grab_clonehero(frame_grabber=session.grab)
    image.save(args.output)
    print(
        f"wrote {args.output} size={image.size[0]}x{image.size[1]} "
        f"mean_luma={mean_luma(image):.1f} max={max_luma(image)} visible={is_visible(image)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
