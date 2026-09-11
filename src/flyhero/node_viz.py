"""Side-panel fly-node firing visualization beside windowed Clone Hero.

Shows reservoir activity (~3k larva neurons) with the six DN-VNC leg neurons
highlighted. GTK DrawingArea on ngram; PIL render for CI / screenshots.
"""

from __future__ import annotations

import math
import subprocess
from collections.abc import Sequence

import numpy as np
from PIL import Image, ImageDraw

LEG_COLORS = (
    (80, 220, 80),  # green fret
    (220, 60, 60),  # red
    (230, 210, 60),  # yellow
    (60, 120, 230),  # blue
    (230, 140, 40),  # orange
    (240, 240, 240),  # strum
)
LEG_LABELS = ("G", "R", "Y", "B", "O", "↓")


def layout_points(n: int, *, width: int, height: int, margin: int = 28) -> np.ndarray:
    """Deterministic spiral layout in panel pixels. Shape (n, 2)."""
    if n < 1:
        raise ValueError("n must be at least 1")
    cx = width * 0.52
    cy = height * 0.48
    max_r = min(width, height) * 0.42 - margin
    pts = np.zeros((n, 2), dtype=np.float32)
    for i in range(n):
        t = i / max(n - 1, 1)
        angle = i * 0.35
        r = max_r * math.sqrt(t)
        pts[i, 0] = cx + r * math.cos(angle)
        pts[i, 1] = cy + r * math.sin(angle)
    return pts


def render_firing(
    state: Sequence[float] | np.ndarray,
    *,
    legs: Sequence[int],
    width: int = 480,
    height: int = 780,
    drive: Sequence[float] | None = None,
    title: str = "Fly Hero — DN-VNC legs",
) -> Image.Image:
    """Paint one frame of the side panel (RGB)."""
    values = np.asarray(state, dtype=np.float32).reshape(-1)
    n = int(values.size)
    pts = layout_points(n, width=width, height=height)
    amp = np.abs(values)
    peak = float(amp.max()) if amp.size else 1.0
    if peak < 1e-6:
        peak = 1.0
    norm = np.clip(amp / peak, 0.0, 1.0)

    img = Image.new("RGB", (width, height), (12, 14, 18))
    draw = ImageDraw.Draw(img)
    draw.text((14, 12), title, fill=(200, 210, 220))
    draw.text((14, 32), f"neurons={n}  peak={peak:.2f}", fill=(140, 150, 160))

    # Dim field first (skip near-zero for speed).
    for i in range(n):
        a = float(norm[i])
        if a < 0.05:
            continue
        x, y = float(pts[i, 0]), float(pts[i, 1])
        c = int(40 + 180 * a)
        r = 1 + int(2 * a)
        draw.ellipse((x - r, y - r, x + r, y + r), fill=(c // 3, c // 2, c))

    # Leg neurons on top.
    for li, idx in enumerate(legs):
        if idx < 0 or idx >= n:
            continue
        color = LEG_COLORS[li % len(LEG_COLORS)]
        x, y = float(pts[idx, 0]), float(pts[idx, 1])
        hot = float(norm[idx])
        r = 6 + int(10 * hot)
        draw.ellipse((x - r, y - r, x + r, y + r), outline=color, width=2)
        if hot > 0.15 or (drive is not None and li < len(drive) and float(drive[li]) > 0):
            draw.ellipse((x - r // 2, y - r // 2, x + r // 2, y + r // 2), fill=color)

    # Legend
    y0 = height - 70
    draw.rectangle((0, y0 - 8, width, height), fill=(8, 10, 12))
    draw.text((14, y0 - 4), "legs (DN-VNC)", fill=(160, 170, 180))
    for li, label in enumerate(LEG_LABELS):
        x = 14 + li * 72
        color = LEG_COLORS[li]
        draw.ellipse((x, y0 + 22, x + 14, y0 + 36), fill=color)
        driven = drive is not None and li < len(drive) and float(drive[li]) > 0
        draw.text((x + 20, y0 + 20), label + (" *" if driven else ""), fill=(220, 220, 220))
    return img


class NodeFiringViz:
    """Live GTK side panel. No-op friendly when display is missing."""

    def __init__(
        self,
        n_neurons: int,
        legs: Sequence[int],
        *,
        width: int = 480,
        height: int = 780,
        title: str = "Fly Hero — node firing",
    ) -> None:
        if n_neurons < 1:
            raise ValueError("n_neurons must be at least 1")
        self.n_neurons = int(n_neurons)
        self.legs = tuple(int(i) for i in legs)
        self.width = int(width)
        self.height = int(height)
        self.title = title
        self._state = np.zeros(self.n_neurons, dtype=np.float32)
        self._drive: np.ndarray | None = None
        self._window = None
        self._image = None
        self._pixbuf = None
        self._closed = False
        self._dirty = True

    def render(self) -> Image.Image:
        return render_firing(
            self._state,
            legs=self.legs,
            width=self.width,
            height=self.height,
            drive=self._drive,
            title=self.title,
        )

    def show(self) -> None:
        """Open the GTK window on the session display."""
        if self._window is not None:
            return
        import gi

        gi.require_version("Gtk", "3.0")
        gi.require_version("GdkPixbuf", "2.0")
        from gi.repository import GdkPixbuf, Gtk

        win = Gtk.Window(title=self.title)
        win.set_default_size(self.width, self.height)
        win.set_keep_above(True)
        win.connect("destroy", self._on_destroy)
        image = Gtk.Image()
        win.add(image)
        win.show_all()
        self._window = win
        self._image = image
        self._Gtk = Gtk
        self._GdkPixbuf = GdkPixbuf
        self._refresh_pixbuf()
        self.place_beside_clonehero()

    def _on_destroy(self, *_args) -> None:
        self._closed = True
        self._window = None
        self._image = None

    def _refresh_pixbuf(self) -> None:
        if self._image is None or self._closed:
            return
        frame = self.render()
        raw = frame.tobytes()
        pb = self._GdkPixbuf.Pixbuf.new_from_data(
            raw,
            self._GdkPixbuf.Colorspace.RGB,
            False,
            8,
            frame.width,
            frame.height,
            frame.width * 3,
        )
        # Keep a reference — Pixbuf.new_from_data does not copy.
        self._pixbuf = pb
        self._image.set_from_pixbuf(pb)

    def update(
        self,
        state: Sequence[float] | np.ndarray,
        *,
        drive: Sequence[float] | None = None,
    ) -> None:
        values = np.asarray(state, dtype=np.float32).reshape(-1)
        if values.size != self.n_neurons:
            raise ValueError(f"state size {values.size} != {self.n_neurons}")
        self._state = values
        self._drive = None if drive is None else np.asarray(drive, dtype=np.float32)
        self._dirty = True

    def pump(self) -> None:
        """Drain pending GTK events without blocking the play loop."""
        if self._window is None or self._closed:
            return
        if self._dirty:
            self._refresh_pixbuf()
            self._dirty = False
        while self._Gtk.events_pending():
            self._Gtk.main_iteration_do(False)

    def place_beside_clonehero(self) -> None:
        if self._window is None:
            return
        try:
            completed = subprocess.run(
                ["xwininfo", "-name", "Clone Hero"],
                check=False,
                capture_output=True,
                text=True,
            )
        except FileNotFoundError:
            return
        if completed.returncode != 0:
            return
        text = completed.stdout
        import re

        abs_x = re.search(r"Absolute upper-left X:\s+(-?\d+)", text)
        abs_y = re.search(r"Absolute upper-left Y:\s+(-?\d+)", text)
        width = re.search(r"Width:\s+(\d+)", text)
        if not (abs_x and abs_y and width):
            return
        x = int(abs_x.group(1)) + int(width.group(1)) + 12
        y = max(40, int(abs_y.group(1)))
        self._window.move(x, y)

    def close(self) -> None:
        if self._window is not None:
            try:
                self._window.destroy()
            except Exception:
                pass
        self._closed = True
        self._window = None
        self._image = None

    def __enter__(self) -> NodeFiringViz:
        self.show()
        return self

    def __exit__(self, *exc) -> None:
        self.close()
