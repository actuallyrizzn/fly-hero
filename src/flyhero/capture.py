"""Grab the Clone Hero window when a desktop is present.

CI never needs this. Tests feed recorded frames. Live play on ngram uses
xwininfo + PIL ImageGrab over Xwayland.
"""

from __future__ import annotations

import os
import re
import subprocess
from collections.abc import Callable
from dataclasses import dataclass

from PIL import Image

XwininfoRunner = Callable[[list[str]], str]


@dataclass(frozen=True)
class WindowBox:
    left: int
    top: int
    width: int
    height: int

    @property
    def bbox(self) -> tuple[int, int, int, int]:
        """PIL ImageGrab bbox: left, top, right, bottom."""
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


def grab_box(box: WindowBox, grabber=None) -> Image.Image:
    if grabber is None:
        from PIL import ImageGrab

        image = ImageGrab.grab(bbox=box.bbox)
    else:
        image = grabber(box.bbox)
    if image.mode != "RGB":
        image = image.convert("RGB")
    return image


def grab_clonehero(*, title: str = "Clone Hero", display: str | None = None) -> Image.Image:
    if display:
        os.environ["DISPLAY"] = display
    return grab_box(find_clonehero_box(title=title))
