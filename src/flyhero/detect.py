"""Decide whether a frame is the Clone Hero highway. No human in the loop."""

from __future__ import annotations

import time

from PIL import Image, ImageDraw

from flyhero.pixel import LANE_RGB, LIVE_COLOR_DISTANCE, classify_pixel

HIGHWAY_TIMEOUT = 45.0


class HighwayTimeout(TimeoutError):
    """Grabber never showed five-lane receptors / gems."""


def paint_receptors(width: int = 200, height: int = 160) -> Image.Image:
    """Synthetic strike-line gems — what ``is_highway`` looks for."""
    if width < 40 or height < 40:
        raise ValueError("receptor image is too small")
    image = Image.new("RGB", (width, height), (8, 8, 8))
    draw = ImageDraw.Draw(image)
    radius = max(6, width // 28)
    cy = int(height * 0.88)
    for index, color in enumerate(LANE_RGB):
        cx = int((index + 0.5) * width / 5)
        draw.ellipse(
            [cx - radius, cy - radius, cx + radius, cy + radius],
            fill=color,
        )
    return image


def is_highway(
    image: Image.Image,
    *,
    min_lanes: int = 3,
    max_distance: float = LIVE_COLOR_DISTANCE,
) -> bool:
    """True when at least ``min_lanes`` gem colors sit in the bottom band."""
    if min_lanes < 1:
        raise ValueError("min_lanes must be at least 1")
    rgb = image.convert("RGB")
    width, height = rgb.size
    if width < 20 or height < 20:
        return False
    pixels = rgb.load()
    found: set[int] = set()
    y0 = int(height * 0.70)
    for lane in range(5):
        x0 = int((lane + 0.25) * width / 5)
        x1 = int((lane + 0.75) * width / 5)
        hits = 0
        total = 0
        step_x = max(1, (x1 - x0) // 10)
        step_y = max(1, (height - y0) // 10)
        for x in range(x0, max(x1, x0 + 1), step_x):
            for y in range(y0, height, step_y):
                total += 1
                if classify_pixel(pixels[x, y], max_distance=max_distance) == lane:
                    hits += 1
        if total and hits / total >= 0.05:
            found.add(lane)
    return len(found) >= min_lanes


def wait_for_highway(
    grab,
    *,
    timeout: float = HIGHWAY_TIMEOUT,
    interval: float = 0.4,
    clock=None,
    sleeper=None,
    detect=is_highway,
) -> Image.Image:
    """Poll ``grab()`` until the highway is visible. Fail closed on timeout."""
    if timeout <= 0:
        raise ValueError("timeout must be positive")
    if interval <= 0:
        raise ValueError("interval must be positive")
    now = clock or time.monotonic
    pause = sleeper or time.sleep
    started = now()
    while now() - started < timeout:
        frame = grab()
        if detect(frame):
            return frame
        pause(interval)
    raise HighwayTimeout("Clone Hero highway did not appear")
