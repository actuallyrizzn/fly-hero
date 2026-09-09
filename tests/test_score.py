from __future__ import annotations

from pathlib import Path

import pytest

from flyhero.chart import load_chart
from flyhero.guitar import GuitarMap, KeyEvent
from flyhero.play import record_chart
from flyhero.score import ScoreReport, score_events, score_log
from flyhero.uinput_hands import RecordingHands

FIXTURE = Path(__file__).parent / "fixtures" / "midtempo.chart"


def test_recorded_fixture_is_accepted():
    chart = load_chart(FIXTURE)
    log = record_chart(chart, step=0.25, look_ahead=1.0, depth=4)
    report = score_log(chart, log, window=0.3)
    assert report.notes == 5
    assert report.hits == 5
    assert report.misses == 0
    assert report.accepted()


def test_idle_log_misses_every_note():
    chart = load_chart(FIXTURE)
    report = score_log(chart, RecordingHands(), window=0.3)
    assert report.hits == 0
    assert report.accuracy == 0.0
    assert report.accepted() is False


def test_open_hold_still_counts():
    chart = load_chart(FIXTURE)
    mapping = GuitarMap()
    events = [
        KeyEvent(0.5, mapping.name(mapping.fret_codes[0]), True),
        KeyEvent(0.5, mapping.name(mapping.strum_code), True),
    ]
    report = score_events(chart, events, mapping=mapping, window=0.05)
    assert report.hits == 1
    doubled = [
        KeyEvent(0.4, mapping.name(mapping.fret_codes[0]), True),
        KeyEvent(0.45, mapping.name(mapping.fret_codes[0]), True),
        KeyEvent(0.5, "other", True),
        KeyEvent(0.5, mapping.name(mapping.strum_code), True),
        KeyEvent(0.6, mapping.name(mapping.fret_codes[0]), False),
        KeyEvent(0.6, mapping.name(mapping.strum_code), False),
    ]
    assert score_events(chart, doubled, mapping=mapping, window=0.05).hits == 1


def test_score_rejects_bad_inputs():
    chart = load_chart(FIXTURE)
    with pytest.raises(ValueError, match="window"):
        score_events(chart, [], window=0)
    empty = load_chart(FIXTURE)
    empty_chart = type(empty)(
        name=empty.name,
        resolution=empty.resolution,
        notes=(),
        duration_seconds=0.0,
    )
    with pytest.raises(ValueError, match="no notes"):
        score_events(empty_chart, [])
    with pytest.raises(ValueError, match="floor"):
        ScoreReport(1, 1, 0, 1.0, 0.3).accepted(floor=2.0)
