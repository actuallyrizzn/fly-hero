from __future__ import annotations

from pathlib import Path

import pytest
from PIL import Image

from flyhero.chart import load_chart
from flyhero.detect import HighwayTimeout, is_highway, paint_receptors, wait_for_highway
from flyhero.highway import encode_highway
from flyhero.pixel import render_highway

FIXTURE = Path(__file__).parent / "fixtures" / "midtempo.chart"


def test_receptors_and_painted_gems_are_highway():
    assert is_highway(paint_receptors())
    chart = load_chart(FIXTURE)
    frame = encode_highway(chart, 0.5, look_ahead=1.0, depth=4)
    assert is_highway(render_highway(frame), min_lanes=1)


def test_dark_and_tiny_are_not_highway():
    assert is_highway(Image.new("RGB", (200, 160), (8, 8, 8))) is False
    assert is_highway(Image.new("RGB", (10, 10), (255, 0, 0))) is False
    with pytest.raises(ValueError, match="small"):
        paint_receptors(10, 10)
    with pytest.raises(ValueError, match="min_lanes"):
        is_highway(paint_receptors(), min_lanes=0)


def test_wait_for_highway_then_timeout():
    frames = [Image.new("RGB", (200, 160), (8, 8, 8)), paint_receptors()]

    def grab():
        return frames.pop(0)

    class Clock:
        def __init__(self) -> None:
            self.t = 0.0

        def now(self) -> float:
            return self.t

        def sleep(self, delay: float) -> None:
            self.t += delay

    clock = Clock()
    seen = wait_for_highway(grab, timeout=2, interval=0.5, clock=clock.now, sleeper=clock.sleep)
    assert is_highway(seen)

    def never():
        return Image.new("RGB", (200, 160), (8, 8, 8))

    clock = Clock()
    with pytest.raises(HighwayTimeout):
        wait_for_highway(never, timeout=1, interval=0.5, clock=clock.now, sleeper=clock.sleep)
    with pytest.raises(ValueError, match="timeout"):
        wait_for_highway(never, timeout=0)
    with pytest.raises(ValueError, match="interval"):
        wait_for_highway(never, interval=0)
