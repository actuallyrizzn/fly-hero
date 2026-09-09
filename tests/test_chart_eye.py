from __future__ import annotations

from pathlib import Path

import pytest

from flyhero.chart import load_chart, parse_chart
from flyhero.chart_eye import ChartEye
from flyhero.highway import encode_highway, render_ascii
from flyhero.train import (
    NearBinReadout,
    collect_samples,
    evaluate,
    label_from_frame,
    play_chart,
)

FIXTURE = Path(__file__).parent / "fixtures" / "midtempo.chart"

MIDTEMPO = """
[Song]
{
  Name = "unit"
  Resolution = 192
}
[SyncTrack]
{
  0 = B 120000
}
[ExpertSingle]
{
  192 = N 0 0
  384 = N 1 0
}
"""


def test_parse_times_at_120_bpm():
    chart = parse_chart(MIDTEMPO)
    assert chart.name == "unit"
    assert chart.resolution == 192
    assert len(chart.notes) == 2
    assert chart.notes[0].lane == 0
    assert chart.notes[0].t_seconds == pytest.approx(0.5)
    assert chart.notes[1].t_seconds == pytest.approx(1.0)
    assert chart.notes_for_lane(1)[0].t_seconds == pytest.approx(1.0)


def test_parse_bpm_change():
    text = """
[Song]
{ Resolution = 192 }
[SyncTrack]
{
  0 = B 120000
  192 = B 60000
}
[ExpertSingle]
{
  384 = N 2 0
}
"""
    chart = parse_chart(text)
    # 192 ticks at 120bpm = 0.5s, then 192 ticks at 60bpm = 1.0s → 1.5s
    assert chart.notes[0].t_seconds == pytest.approx(1.5)


def test_parse_skips_open_notes_and_comments():
    text = """
[Song]
{
  Name = 'x'
  Resolution = 192
}
[SyncTrack]
{ 0 = B 120000 }
[ExpertSingle]
{
  0 = N 7 0
  192 = N 0 0 // green
}
"""
    chart = parse_chart(text)
    assert [n.lane for n in chart.notes] == [0]


def test_parse_rejects_bad_resolution_and_bpm():
    with pytest.raises(ValueError, match="Resolution"):
        parse_chart("[Song]\n{\nResolution = 0\n}\n[SyncTrack]\n{\n0 = B 120000\n}\n")
    with pytest.raises(ValueError, match="Resolution"):
        parse_chart("[Song]\n{\nResolution = nope\n}\n")
    with pytest.raises(ValueError, match="BPM"):
        parse_chart("[Song]\n{\nResolution = 192\n}\n[SyncTrack]\n{\n0 = B 0\n}\n")


def test_offset_and_sustain_and_late_bpm():
    text = """
[Song]
{
  Name = "held"
  Offset = 1
  Resolution = 192
}
[SyncTrack]
{
  192 = B 120000
}
[ExpertSingle]
{
  192 = N 3 192
}
"""
    chart = parse_chart(text)
    assert chart.notes[0].t_seconds == pytest.approx(1.5)
    assert chart.notes[0].sustain_seconds == pytest.approx(0.5)
    held = encode_highway(chart, 1.6, look_ahead=1.0, depth=4)
    assert held.cells[3][0] == 1.0


def test_missing_track_is_empty_chart():
    chart = parse_chart("[Song]\n{ Resolution = 192 }\n[SyncTrack]\n{ 0 = B 120000 }\n")
    assert chart.notes == ()
    assert chart.duration_seconds == 0.0


def test_default_bpm_when_sync_missing():
    chart = parse_chart(
        "noise before sections\n[Song]\n{\nResolution = 192\n}\n[ExpertSingle]\n{\n192 = N 4 0\n0 = E solo\n}\n"
    )
    assert chart.notes[0].t_seconds == pytest.approx(0.5)
    assert chart.notes[0].lane == 4
    zero = parse_chart(
        "[Song]\n{\nName = untitled\nOffset =\nResolution = 192\n}\n[SyncTrack]\n{\n0 = TS 4\n0 = B 120000\n}\n[ExpertSingle]\n{\n0 = N 2 0\n}\n"
    )
    assert zero.notes[0].t_seconds == pytest.approx(0.0)
    assert zero.name == "untitled"


def test_highway_places_gem_by_distance_not_clock():
    chart = parse_chart(MIDTEMPO)
    far = encode_highway(chart, 0.0, look_ahead=1.0, depth=4)
    assert far.cells[0][2] == 1.0
    assert far.cells[1][3] == 1.0
    strike = encode_highway(chart, 0.5, look_ahead=1.0, depth=4)
    assert strike.cells[0][0] == 1.0
    assert strike.cells[1][2] == 1.0


def test_highway_rejects_bad_params():
    chart = parse_chart(MIDTEMPO)
    with pytest.raises(ValueError, match="look_ahead"):
        encode_highway(chart, 0.0, look_ahead=0)
    with pytest.raises(ValueError, match="depth"):
        encode_highway(chart, 0.0, depth=0)


def test_ascii_golden_midtempo_t0():
    chart = load_chart(FIXTURE)
    eye = ChartEye(chart, look_ahead=1.0, depth=4)
    picture = render_ascii(eye.see(0.0))
    expected = "\n".join(
        [
            "G|..#.|",
            "R|...#|",
            "Y|....|",
            "B|....|",
            "O|....|",
        ]
    )
    assert picture == expected


def test_label_and_near_bin_readout():
    chart = parse_chart(MIDTEMPO)
    frame = encode_highway(chart, 0.5, look_ahead=1.0, depth=4)
    action = label_from_frame(frame)
    assert action.frets[0] is True
    assert action.strum is True
    pred = NearBinReadout().act(frame.as_vector())
    assert pred == action
    with pytest.raises(ValueError, match="too short"):
        NearBinReadout().act([0.0, 0.0])
    with pytest.raises(ValueError, match="full highway"):
        NearBinReadout().act([0.0] * 6)


def test_evaluate_features_only_is_perfect():
    chart = load_chart(FIXTURE)
    stats = evaluate(chart, step=0.1, look_ahead=1.0, depth=4)
    assert stats["total"] > 0
    assert stats["accuracy"] == pytest.approx(1.0)


def test_collect_and_play():
    chart = parse_chart(MIDTEMPO)
    with pytest.raises(ValueError, match="step"):
        collect_samples(chart, step=0)
    samples = collect_samples(chart, step=0.25, look_ahead=1.0, depth=4)
    assert samples[0].frame.t_seconds == 0.0
    actions = play_chart(chart, step=0.25, look_ahead=1.0, depth=4)
    assert len(actions) == len(samples)
    assert any(a.strum for a in actions)
