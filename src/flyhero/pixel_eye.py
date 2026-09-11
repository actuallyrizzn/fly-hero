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
from flyhero.eye import Eye
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


class ThreadedEye:
    """Keep grabbing and decoding in the background; ``see`` returns the latest frame.

    The capture path is slow (hundreds of ms). The player ticks every 20 ms and
    must never block on it. ``see`` is what the fly saw most recently — a lagging
    camera, the same shape ``DelayedEye`` trains against.
    """

    def __init__(self, inner: Eye, *, depth: int = DEFAULT_DEPTH, on_error=None) -> None:
        import threading

        self.inner = inner
        self.depth = depth
        self.on_error = on_error
        self.frames = 0
        self.errors = 0
        self.stale = 0
        self.latest: FeatureFrame = FeatureFrame.empty(depth=depth)
        self.latest_image: Image.Image | None = None
        self._last_digest: bytes | None = None
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._threading = threading

    def start(self) -> ThreadedEye:
        if self._thread is None:
            self._thread = self._threading.Thread(target=self._loop, name="flyhero-eye", daemon=True)
            self._thread.start()
        return self

    def _loop(self) -> None:
        import hashlib

        while not self._stop.is_set():
            try:
                image = None
                if hasattr(self.inner, "grab"):
                    # Keep the Screencast file short so remux+sseof stays cheap.
                    session = getattr(getattr(self.inner, "session", None), "restart", None)
                    if callable(session) and self.frames > 0 and self.frames % 6 == 0:
                        try:
                            self.inner.session.restart()
                        except Exception:
                            pass
                    image = self.inner.grab()
                    digest = hashlib.sha1(image.tobytes()).digest()
                    if digest == self._last_digest:
                        self.stale += 1
                        # Same pixels as last grab — wait and try again (frozen webm).
                        if self.stale >= 3 and callable(session):
                            try:
                                self.inner.session.restart()
                            except Exception:
                                pass
                            self._last_digest = None
                        self._stop.wait(0.02)
                        continue
                    self._last_digest = digest
                    self.latest_image = image
                    if hasattr(self.inner, "see_image"):
                        self.latest = self.inner.see_image(image, 0.0)
                    else:
                        self.latest = self.inner.see(0.0)
                else:
                    self.latest = self.inner.see(0.0)
                self.frames += 1
            except Exception as exc:  # capture hiccups must not kill the player
                self.errors += 1
                if self.on_error is not None:
                    self.on_error(exc)
                self._stop.wait(0.05)

    def see(self, t_seconds: float) -> FeatureFrame:
        frame = self.latest
        return FeatureFrame(cells=frame.cells, t_seconds=t_seconds)

    def close(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=2.0)
            self._thread = None

    def __enter__(self) -> ThreadedEye:
        return self.start()

    def __exit__(self, *exc) -> None:
        self.close()


class TrapezoidEye:
    """Fair eye for live Clone Hero: trapezoid decode (same contract as ChartEye)."""

    def __init__(
        self,
        source: ImageSource,
        *,
        depth: int = DEFAULT_DEPTH,
        roi=None,
    ) -> None:
        from flyhero.pixel import TrapezoidRoi, decode_trapezoid

        if depth < 1:
            raise ValueError("depth must be at least 1")
        self.source = source
        self.depth = depth
        self.roi = roi or TrapezoidRoi()
        self._decode = decode_trapezoid

    def _image_at(self, t_seconds: float) -> Image.Image:
        source = self.source
        if callable(source):
            return source(t_seconds)
        if isinstance(source, Image.Image):
            return source
        return Image.open(source)

    def see(self, t_seconds: float) -> FeatureFrame:
        return self._decode(
            self._image_at(t_seconds),
            depth=self.depth,
            t_seconds=t_seconds,
            roi=self.roi,
        )

    def see_image(self, image: Image.Image, t_seconds: float) -> FeatureFrame:
        return self._decode(
            image, depth=self.depth, t_seconds=t_seconds, roi=self.roi
        )


class WindowCastEye:
    """Live fair eye: long-lived Shell.Screencast → crop Clone Hero → trapezoid.

    Default path for ``play_prosthesis --pixels``. PipeWire gst-launch on ngram
    negotiates YUY2 and scrambles; do not use that here. Optional ``scale``
    downsamples before decode to keep ThreadedEye cheap.
    """

    def __init__(
        self,
        session,
        *,
        depth: int = DEFAULT_DEPTH,
        scale: float = 0.5,
        roi=None,
    ) -> None:
        from flyhero.pixel import TrapezoidRoi

        if depth < 1:
            raise ValueError("depth must be at least 1")
        if scale <= 0:
            raise ValueError("scale must be positive")
        self.session = session
        self.depth = depth
        self.scale = float(scale)
        self.roi = roi or TrapezoidRoi()
        self.last_image: Image.Image | None = None
        self._lock = __import__("threading").Lock()

    def grab(self) -> Image.Image:
        from flyhero.capture import grab_clonehero

        with self._lock:
            image = grab_clonehero(frame_grabber=self.session.grab)
            if self.scale != 1.0:
                size = (
                    max(8, int(image.width * self.scale)),
                    max(8, int(image.height * self.scale)),
                )
                image = image.resize(size, Image.Resampling.BOX)
            self.last_image = image
            return image

    def see_image(self, image: Image.Image, t_seconds: float) -> FeatureFrame:
        from flyhero.pixel import decode_trapezoid

        return decode_trapezoid(
            image, depth=self.depth, t_seconds=t_seconds, roi=self.roi
        )

    def see(self, t_seconds: float) -> FeatureFrame:
        return self.see_image(self.grab(), t_seconds)


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
