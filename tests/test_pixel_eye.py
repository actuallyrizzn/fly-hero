from __future__ import annotations

import os
from pathlib import Path

import pytest
from PIL import Image, ImageGrab

from flyhero.capture import WindowBox, find_clonehero_box, grab_box, grab_clonehero, parse_xwininfo
from flyhero.chart import load_chart
from flyhero.chart_eye import ChartEye
from flyhero.hands import NullHands
from flyhero.highway import render_ascii
from flyhero.pixel import (
    HIGHWAY_RGB,
    LANE_RGB,
    HighwayRoi,
    classify_pixel,
    decode_highway,
    render_highway,
)
from flyhero.pixel_eye import LivePixelEye, PixelEye
from flyhero.player import Player
from flyhero.readout import ThresholdReadout
from flyhero.reservoir import NullReservoir
from flyhero.train import NearBinReadout, label_from_frame
from flyhero.types import FeatureFrame

FIXTURE_CHART = Path(__file__).parent / "fixtures" / "midtempo.chart"
GOLDEN_PNG = Path(__file__).parent / "fixtures" / "highway_midtempo_t0.png"
XWININFO = """
xwininfo: Window id: 0x1a00007 "Clone Hero"

  Absolute upper-left X:  120
  Absolute upper-left Y:  80
  Relative upper-left X:  0
  Relative upper-left Y:  0
  Width: 1280
  Height: 720
  Depth: 24
  Visual: 0x21
"""


def midtempo_frame() -> FeatureFrame:
    eye = ChartEye(load_chart(FIXTURE_CHART), look_ahead=1.0, depth=4)
    return eye.see(0.0)


def test_render_decode_round_trip_matches_chart_eye():
    expected = midtempo_frame()
    image = render_highway(expected)
    got = decode_highway(image, depth=4, t_seconds=0.0)
    assert got.cells == expected.cells
    assert render_ascii(got) == render_ascii(expected)


def test_pixel_eye_on_recorded_highway_matches_ascii_golden():
    expected = midtempo_frame()
    image = render_highway(expected)
    GOLDEN_PNG.parent.mkdir(parents=True, exist_ok=True)
    image.save(GOLDEN_PNG)
    eye = PixelEye(GOLDEN_PNG, depth=4)
    picture = render_ascii(eye.see(0.0))
    assert picture == "\n".join(
        [
            "G|..#.|",
            "R|...#|",
            "Y|....|",
            "B|....|",
            "O|....|",
        ]
    )


def test_pixel_eye_drives_same_player_as_chart_eye():
    frame = midtempo_frame()
    eye = PixelEye(render_highway(frame), depth=4)
    player = Player(
        eye=eye,
        reservoir=NullReservoir(size=20),
        readout=NearBinReadout(),
        hands=NullHands(),
    )
    action = player.tick(0.0)
    assert action == label_from_frame(frame)


def test_live_eye_uses_roi_and_callback():
    inner = render_highway(midtempo_frame(), cell=20)
    canvas = Image.new("RGB", (400, 320), (8, 8, 8))
    canvas.paste(inner, (80, 60))

    def grab(_t: float) -> Image.Image:
        return canvas

    roi = HighwayRoi(left=80 / 400, top=60 / 320, right=(80 + inner.size[0]) / 400, bottom=(60 + inner.size[1]) / 320)
    eye = LivePixelEye(grab, depth=4, roi=roi)
    assert eye.see(1.25).t_seconds == 1.25
    assert eye.see(1.25).cells == midtempo_frame().cells


def test_classify_and_roi_guards():
    assert classify_pixel(LANE_RGB[0]) == 0
    assert classify_pixel(HIGHWAY_RGB) is None
    with pytest.raises(ValueError, match="RGB"):
        classify_pixel((9,))
    with pytest.raises(ValueError, match="left/right"):
        HighwayRoi(left=0.9, right=0.1)
    with pytest.raises(ValueError, match="top/bottom"):
        HighwayRoi(top=0.9, bottom=0.1)
    with pytest.raises(ValueError, match="cell"):
        render_highway(FeatureFrame.empty(depth=2), cell=2)
    with pytest.raises(ValueError, match="depth"):
        decode_highway(render_highway(FeatureFrame.empty(depth=2)), depth=0)
    tiny = Image.new("RGB", (3, 3), HIGHWAY_RGB)
    with pytest.raises(ValueError, match="too small"):
        decode_highway(tiny, depth=8)
    with pytest.raises(ValueError, match="depth"):
        PixelEye(tiny, depth=0)


def test_player_threshold_from_pixels():
    rows = [[1.0], [0.0], [0.0], [0.0], [0.0]]
    frame = FeatureFrame.from_rows(rows)
    eye = PixelEye(lambda _: render_highway(frame, cell=16), depth=1)
    player = Player(
        eye=eye,
        reservoir=NullReservoir(size=5),
        readout=ThresholdReadout(threshold=0.5),
        hands=NullHands(),
    )
    assert player.tick(3.0).frets[0] is True


def test_parse_xwininfo_and_injected_grab():
    box = parse_xwininfo(XWININFO)
    assert box == WindowBox(left=120, top=80, width=1280, height=720)
    assert box.bbox == (120, 80, 1400, 800)
    found = find_clonehero_box(runner=lambda cmd: XWININFO if cmd[0] == "xwininfo" else "")
    assert found.width == 1280
    with pytest.raises(ValueError, match="geometry"):
        parse_xwininfo("nope")

    painted = render_highway(midtempo_frame())

    def fake_grab(bbox):
        assert bbox == box.bbox
        return painted

    assert grab_box(box, grabber=fake_grab).size == painted.size
    converted = grab_box(box, grabber=lambda _: painted.convert("RGBA"))
    assert converted.mode == "RGB"


def test_find_clonehero_via_subprocess(monkeypatch):
    class Result:
        returncode = 0
        stdout = XWININFO
        stderr = ""

    monkeypatch.setattr("flyhero.capture.subprocess.run", lambda *a, **k: Result())
    assert find_clonehero_box().width == 1280


def test_find_clonehero_missing(monkeypatch):
    class Result:
        returncode = 1
        stdout = ""
        stderr = "xwininfo: No window with name"

    monkeypatch.setattr("flyhero.capture.subprocess.run", lambda *a, **k: Result())
    with pytest.raises(FileNotFoundError, match="No window"):
        find_clonehero_box()


def test_grab_box_uses_imagegrab(monkeypatch):
    painted = render_highway(midtempo_frame())
    monkeypatch.setattr(ImageGrab, "grab", lambda bbox=None: painted)
    box = WindowBox(0, 0, painted.size[0], painted.size[1])
    assert grab_box(box).size == painted.size


def test_grab_clonehero_sets_display(monkeypatch):
    painted = render_highway(midtempo_frame())
    monkeypatch.setattr(
        "flyhero.capture.find_clonehero_box",
        lambda title="Clone Hero": WindowBox(0, 0, painted.size[0], painted.size[1]),
    )
    previous = os.environ.get("DISPLAY")
    try:
        image = grab_clonehero(display=":9", frame_grabber=lambda: painted)
        assert os.environ["DISPLAY"] == ":9"
        assert image.size == painted.size
    finally:
        if previous is None:
            os.environ.pop("DISPLAY", None)
        else:
            os.environ["DISPLAY"] = previous
