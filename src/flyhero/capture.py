"""Grab the Clone Hero window when a desktop is present.

CI never needs this. Tests feed recorded frames.

Live play on ngram uses Mutter ScreenCast → PipeWire (clean RGB), then
crops with xwininfo geometry. X11 ImageGrab of Unity is black — do not
use it as the fair eye.
"""

from __future__ import annotations

import os
import re
import subprocess
from collections.abc import Callable
from dataclasses import dataclass

from PIL import Image

from flyhero.pipewire import grab_desktop_frame
from flyhero.visibility import require_visible

XwininfoRunner = Callable[[list[str]], str]
FrameGrabber = Callable[[], Image.Image]


@dataclass(frozen=True)
class WindowBox:
    left: int
    top: int
    width: int
    height: int

    @property
    def bbox(self) -> tuple[int, int, int, int]:
        """left, top, right, bottom in the same space as the frame."""
        return (self.left, self.top, self.left + self.width, self.top + self.height)


_ABS_RE = re.compile(
    r"Absolute upper-left X:\s+(-?\d+).*?Absolute upper-left Y:\s+(-?\d+)",
    re.S,
)
_GEO_RE = re.compile(r"Width:\s+(\d+).*?Height:\s+(\d+)", re.S)


def parse_xwininfo(text: str) -> WindowBox:
    """Parse `xwininfo -name …` output. No shell."""
    abs_match = _ABS_RE.search(text)
    geo_match = _GEO_RE.search(text)
    if not abs_match or not geo_match:
        raise ValueError("xwininfo output is missing geometry")
    return WindowBox(
        left=int(abs_match.group(1)),
        top=int(abs_match.group(2)),
        width=int(geo_match.group(1)),
        height=int(geo_match.group(2)),
    )


def find_clonehero_box(
    *,
    title: str = "Clone Hero",
    runner: XwininfoRunner | None = None,
) -> WindowBox:
    command = ["xwininfo", "-name", title]
    if runner is None:
        completed = subprocess.run(command, check=False, capture_output=True, text=True)
        if completed.returncode != 0:
            raise FileNotFoundError(completed.stderr.strip() or "Clone Hero window not found")
        text = completed.stdout
    else:
        text = runner(command)
    return parse_xwininfo(text)


def crop_to_box(
    image: Image.Image,
    box: WindowBox,
    *,
    screen_size: tuple[int, int] | None = None,
) -> Image.Image:
    """Crop a monitor frame to the Clone Hero window. Scales if stream ≠ screen."""
    width, height = image.size
    screen_w, screen_h = screen_size or (width, height)
    if screen_w <= 0 or screen_h <= 0:
        raise ValueError("screen size must be positive")
    scale_x = width / screen_w
    scale_y = height / screen_h
    left = max(0, int(round(box.left * scale_x)))
    top = max(0, int(round(box.top * scale_y)))
    right = min(width, int(round((box.left + box.width) * scale_x)))
    bottom = min(height, int(round((box.top + box.height) * scale_y)))
    if right - left < 8 or bottom - top < 8:
        return image
    cropped = image.crop((left, top, right, bottom))
    return cropped.convert("RGB") if cropped.mode != "RGB" else cropped


def grab_box(box: WindowBox, grabber=None) -> Image.Image:
    """Legacy X11 grab. Kept for tests. Live eye must not use this."""
    if grabber is None:
        from PIL import ImageGrab

        image = ImageGrab.grab(bbox=box.bbox)
    else:
        image = grabber(box.bbox)
    if image.mode != "RGB":
        image = image.convert("RGB")
    return image


def grab_clonehero(
    *,
    title: str = "Clone Hero",
    display: str | None = None,
    frame_grabber: FrameGrabber | None = None,
    box_finder: Callable[..., WindowBox] | None = None,
    screen_size: tuple[int, int] | None = None,
) -> Image.Image:
    """PipeWire monitor frame, cropped to the Clone Hero window when found."""
    if display:
        os.environ["DISPLAY"] = display
    image = require_visible((frame_grabber or grab_desktop_frame)())
    finder = box_finder or find_clonehero_box
    try:
        box = finder(title=title)
    except TypeError:
        box = finder()
    except FileNotFoundError:
        return image
    return crop_to_box(image, box, screen_size=screen_size)
