"""EventWriter unit tests."""

from __future__ import annotations

from pathlib import Path

from flyhero.events import EventWriter


def test_event_writer_jsonl(tmp_path: Path):
    path = tmp_path / "events.jsonl"
    w = EventWriter(path)
    w.song_start(song="Midtempo", track="EasySingle")
    w.action_edges((False,) * 5, False)
    w.action_edges((True, False, False, False, False), True)
    w.song_end()
    w.score(hits=33, notes=39, score=1, max_streak=8, accuracy=33 / 39)
    lines = path.read_text(encoding="utf-8").strip().splitlines()
    assert any("SONG_START" in ln for ln in lines)
    assert any("HIT" in ln for ln in lines)
    assert any("SCORE" in ln for ln in lines)


def test_event_writer_noop():
    w = EventWriter(None)
    assert not w.enabled
    w.song_start()
    w.action_edges((True,) * 5, True)
