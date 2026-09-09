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


def _column_lanes(
    rgb: Image.Image,
    *,
    x0: int,
    x1: int,
    y0: int,
    y1: int,
    max_distance: float,
    min_ratio: float,
) -> set[int]:
    width = max(x1 - x0, 1)
    height = max(y1 - y0, 1)
    pixels = rgb.load()
    found: set[int] = set()
    for lane in range(5):
        lx0 = x0 + int((lane + 0.25) * width / 5)
        lx1 = x0 + int((lane + 0.75) * width / 5)
        hits = 0
        total = 0
        step_x = max(1, (lx1 - lx0) // 10)
        step_y = max(1, height // 10)
        for x in range(lx0, max(lx1, lx0 + 1), step_x):
            for y in range(y0, y1, step_y):
                total += 1
                if classify_pixel(pixels[x, y], max_distance=max_distance) == lane:
                    hits += 1
        if total and hits / total >= min_ratio:
            found.add(lane)
    return found


def _color_lanes(
    rgb: Image.Image,
    *,
    xf0: float,
    xf1: float,
    yf0: float,
    yf1: float,
    max_distance: float,
    step: int = 3,
) -> set[int]:
    width, height = rgb.size
    pixels = rgb.load()
    found: set[int] = set()
    for y in range(int(height * yf0), max(int(height * yf1), int(height * yf0) + 1), step):
        for x in range(int(width * xf0), max(int(width * xf1), int(width * xf0) + 1), step):
            lane = classify_pixel(pixels[x, y], max_distance=max_distance)
            if lane is not None:
                found.add(lane)
    return found


def is_highway(
    image: Image.Image,
    *,
    min_lanes: int = 3,
    max_distance: float = LIVE_COLOR_DISTANCE,
) -> bool:
    """True when gem colors sit on a highway — synthetic or live windowed."""
    if min_lanes < 1:
        raise ValueError("min_lanes must be at least 1")
    rgb = image.convert("RGB")
    width, height = rgb.size
    if width < 20 or height < 20:
        return False
    bottom = _column_lanes(
        rgb,
        x0=0,
        x1=width,
        y0=int(height * 0.70),
        y1=height,
        max_distance=max_distance,
        min_ratio=0.05,
    )
    if len(bottom) >= min_lanes:
        return True
    # Whole-desktop grab: Clone Hero is a centered window. Menu chrome
    # lives at the edges; gems sit in the inner highway.
    inner = _color_lanes(
        rgb,
        xf0=0.32,
        xf1=0.68,
        yf0=0.30,
        yf1=0.70,
        max_distance=max_distance,
    )
    return len(inner) >= min_lanes


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
