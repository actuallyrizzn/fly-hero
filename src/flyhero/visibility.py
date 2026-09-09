"""Reject black / dead frames. X11 grabs of Unity look like this."""

from __future__ import annotations

from PIL import Image

# ImageGrab of an Xwayland Unity window is ~0. A live highway is also dark
# (mean ~7) but gems still light a few pixels. Dead grabs are max≈0.
MIN_MEAN_LUMA = 1.0
MIN_MAX_LUMA = 16.0


def mean_luma(image: Image.Image) -> float:
    gray = image.convert("L")
    hist = gray.histogram()
    total = sum(hist)
    if total == 0:
        return 0.0
    return sum(i * n for i, n in enumerate(hist)) / total


def max_luma(image: Image.Image) -> int:
    return image.convert("L").getextrema()[1]


def is_visible(image: Image.Image) -> bool:
    """True when the frame has real picture, not a black pixmap."""
    return mean_luma(image) >= MIN_MEAN_LUMA and max_luma(image) >= MIN_MAX_LUMA


def require_visible(image: Image.Image) -> Image.Image:
    if image.mode != "RGB":
        image = image.convert("RGB")
    if not is_visible(image):
        raise RuntimeError(
            "capture is black (X11/Unity pixmap or a dead PipeWire stream). "
            "Use Mutter/PipeWire, not ImageGrab."
        )
    return image
