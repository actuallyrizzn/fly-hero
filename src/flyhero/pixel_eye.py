"""Fair eye: pixels in → FeatureFrame out. Same contract as ChartEye."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from PIL import Image

from flyhero.pixel import (
    LIVE_COLOR_DISTANCE,
    MAX_COLOR_DISTANCE,
    HighwayRoi,
    decode_highway,
)
from flyhero.types import DEFAULT_DEPTH, FeatureFrame

ImageSource = Image.Image | Path | str | Callable[[float], Image.Image]


class PixelEye:
    """See a highway photograph (file, PIL image, or capture callback)."""

    def __init__(
        self,
        source: ImageSource,
        *,
        depth: int = DEFAULT_DEPTH,
        roi: HighwayRoi | None = None,
        max_distance: float = MAX_COLOR_DISTANCE,
    ) -> None:
        if depth < 1:
            raise ValueError("depth must be at least 1")
        self.source = source
        self.depth = depth
        self.roi = roi
        self.max_distance = max_distance

    def _image_at(self, t_seconds: float) -> Image.Image:
        source = self.source
        if callable(source):
            return source(t_seconds)
        if isinstance(source, Image.Image):
            return source
        return Image.open(source)

    def see(self, t_seconds: float) -> FeatureFrame:
        return decode_highway(
            self._image_at(t_seconds),
            depth=self.depth,
            t_seconds=t_seconds,
            roi=self.roi,
            max_distance=self.max_distance,
        )


class LivePixelEye(PixelEye):
    """Same decoder, looser color tolerance for a real Clone Hero window."""

    def __init__(
        self,
        source: ImageSource,
        *,
        depth: int = DEFAULT_DEPTH,
        roi: HighwayRoi | None = None,
        max_distance: float = LIVE_COLOR_DISTANCE,
    ) -> None:
        super().__init__(
            source,
            depth=depth,
            roi=roi if roi is not None else HighwayRoi(),
            max_distance=max_distance,
        )
