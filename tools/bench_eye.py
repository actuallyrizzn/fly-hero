#!/usr/bin/env python3
"""Measure live eye grab latency + unique-frame rate on ngram.

  PYTHONPATH=src .venv/bin/python -u tools/bench_eye.py --seconds 8
  PYTHONPATH=src .venv/bin/python -u tools/bench_eye.py --fullhd --seconds 5
  PYTHONPATH=src .venv/bin/python -u tools/bench_eye.py --cast --seconds 8

Gate (fast640 default): unique_hz >= 5 and mean_ms <= 200 on a live desktop.
"""

from __future__ import annotations

import argparse
import hashlib
import os
import statistics
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


def _env() -> None:
    os.environ.setdefault("DISPLAY", ":0")
    runtime = os.environ.get("XDG_RUNTIME_DIR", "/run/user/1000")
    os.environ.setdefault("XDG_RUNTIME_DIR", runtime)
    if "XAUTHORITY" not in os.environ:
        auths = sorted(Path(runtime).glob(".mutter-Xwaylandauth.*"))
        if auths:
            os.environ["XAUTHORITY"] = str(auths[-1])


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seconds", type=float, default=8.0)
    parser.add_argument("--fullhd", action="store_true", help="1080p snapshot pipeline")
    parser.add_argument("--cast", action="store_true", help="rolling Shell.Screencast webm")
    parser.add_argument("--scale", type=float, default=1.0)
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args()
    _env()

    from flyhero.capture import grab_clonehero
    from flyhero.pixel_eye import WindowCastEye
    from flyhero.pipewire import ScreenCastSession
    from flyhero.shellcast import (
        SNAPSHOT_PIPELINE,
        SNAPSHOT_PIPELINE_FAST,
        QuietBanners,
        clear_remote_desktop,
        snapshot_frame,
        stop_screencast,
    )

    stop_screencast()
    banners = QuietBanners()
    banners.__enter__()
    clear_remote_desktop(tries=4)

    cast = None
    if args.cast:
        cast = ScreenCastSession()
        cast.start()
        clear_remote_desktop(tries=4)
        eye = WindowCastEye(cast, depth=8, scale=args.scale)
        grab = eye.grab
        label = "rolling-cast"
    else:
        pipe = SNAPSHOT_PIPELINE if args.fullhd else SNAPSHOT_PIPELINE_FAST

        def grab():
            desktop = snapshot_frame(wait=0.0, pipeline=pipe)
            image = grab_clonehero(frame_grabber=lambda: desktop)
            if args.scale != 1.0:
                from PIL import Image

                size = (
                    max(8, int(image.width * args.scale)),
                    max(8, int(image.height * args.scale)),
                )
                image = image.resize(size, Image.Resampling.BOX)
            return image

        label = "fullhd" if args.fullhd else "fast640"

    times: list[float] = []
    digests: set[bytes] = set()
    errors = 0
    deadline = time.monotonic() + max(0.5, args.seconds)
    while time.monotonic() < deadline:
        t0 = time.perf_counter()
        try:
            image = grab()
            ms = (time.perf_counter() - t0) * 1000.0
            times.append(ms)
            digests.add(hashlib.sha1(image.tobytes()).digest())
        except Exception as exc:  # noqa: BLE001
            errors += 1
            print(f"error: {exc}", flush=True)
            time.sleep(0.1)

    rolls = 0
    if cast is not None:
        rolls = int(getattr(getattr(cast, "_shell", None), "rolls", 0) or 0)
        cast.close()
    banners.__exit__(None, None, None)
    stop_screencast()

    n = len(times)
    unique = len(digests)
    elapsed = max(args.seconds, 1e-6)
    mean_ms = statistics.mean(times) if times else float("nan")
    p50 = statistics.median(times) if times else float("nan")
    line = (
        f"eye_bench mode={label} grabs={n} unique={unique} "
        f"unique_hz={unique / elapsed:.2f} grab_hz={n / elapsed:.2f} "
        f"mean_ms={mean_ms:.1f} p50_ms={p50:.1f} errors={errors} rolls={rolls}"
    )
    print(line, flush=True)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(line + "\n", encoding="utf-8")
    if label == "fast640" and n > 0:
        if unique / elapsed < 5.0 or mean_ms > 200.0:
            return 2
    return 0 if n > 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
