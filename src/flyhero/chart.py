"""Parse a Clone Hero ``notes.chart`` into timed fret events.

Times in this module are for placing gems on a picture. They are not player inputs.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

_SECTION = re.compile(r"^\[(?P<name>[^\]]+)\]\s*$")
_KV = re.compile(r"^\s*(?P<key>[^=]+?)=\s*(?P<value>.*?)\s*$")
_EV = re.compile(
    r"^\s*(?P<tick>\d+)\s*=\s*(?P<kind>[A-Za-z]+)\s+(?P<rest>.+?)\s*$"
)


@dataclass(frozen=True)
class NoteEvent:
    t_seconds: float
    lane: int
    sustain_seconds: float


@dataclass(frozen=True)
class Chart:
    name: str
    resolution: int
    notes: tuple[NoteEvent, ...]
    duration_seconds: float

    def notes_for_lane(self, lane: int) -> tuple[NoteEvent, ...]:
        return tuple(n for n in self.notes if n.lane == lane)


def _unquote(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
        return value[1:-1]
    return value


def _parse_sections(text: str) -> dict[str, list[str]]:
    sections: dict[str, list[str]] = {}
    current: str | None = None
    for raw in text.splitlines():
        line = raw.split("//", 1)[0].strip().strip("{}").strip()
        if not line:
            continue
        match = _SECTION.match(line)
        if match:
            current = match.group("name")
            sections.setdefault(current, [])
            continue
        if current is None:
            continue
        sections[current].append(line)
    return sections


def _bpm_segments(sync_lines: list[str], resolution: int) -> list[tuple[int, float]]:
    """Return (tick, seconds_per_tick) segments, sorted."""
    beats: list[tuple[int, float]] = []
    for line in sync_lines:
        match = _EV.match(line)
        if not match or match.group("kind") != "B":
            continue
        tick = int(match.group("tick"))
        bpm = float(match.group("rest").split()[0]) / 1000.0
        if bpm <= 0:
            raise ValueError(f"non-positive BPM at tick {tick}")
        seconds_per_tick = (60.0 / bpm) / resolution
        beats.append((tick, seconds_per_tick))
    if not beats:
        beats.append((0, (60.0 / 120.0) / resolution))
    beats.sort(key=lambda item: item[0])
    if beats[0][0] != 0:
        beats.insert(0, (0, beats[0][1]))
    return beats


def _ticks_to_seconds(tick: int, segments: list[tuple[int, float]]) -> float:
    seconds = 0.0
    for i, (start, spt) in enumerate(segments):
        end = segments[i + 1][0] if i + 1 < len(segments) else tick
        if tick <= start:
            break
        span = min(tick, end) - start
        if span > 0:
            seconds += span * spt
        if tick <= end:
            break
    return seconds


def parse_chart(text: str, track: str = "ExpertSingle") -> Chart:
    sections = _parse_sections(text)
    song_meta = {}
    for line in sections.get("Song", []):
        kv = _KV.match(line)
        if kv:
            song_meta[kv.group("key").strip()] = _unquote(kv.group("value"))
    try:
        resolution = int(float(song_meta.get("Resolution", "192")))
    except ValueError as exc:
        raise ValueError("Resolution must be an integer") from exc
    if resolution < 1:
        raise ValueError("Resolution must be at least 1")
    offset = float(song_meta.get("Offset", "0") or 0)
    name = song_meta.get("Name", "untitled")
    segments = _bpm_segments(sections.get("SyncTrack", []), resolution)
    notes: list[NoteEvent] = []
    for line in sections.get(track, []):
        match = _EV.match(line)
        if not match or match.group("kind") != "N":
            continue
        parts = match.group("rest").split()
        if len(parts) < 1:
            continue
        fret = int(parts[0])
        if fret < 0 or fret > 4:
            continue
        sustain_ticks = int(parts[1]) if len(parts) > 1 else 0
        tick = int(match.group("tick"))
        t = _ticks_to_seconds(tick, segments) + offset
        sustain = _ticks_to_seconds(tick + max(sustain_ticks, 0), segments) - (
            t - offset
        )
        notes.append(NoteEvent(t_seconds=t, lane=fret, sustain_seconds=max(sustain, 0.0)))
    notes.sort(key=lambda n: (n.t_seconds, n.lane))
    last = notes[-1].t_seconds if notes else 0.0
    return Chart(
        name=name,
        resolution=resolution,
        notes=tuple(notes),
        duration_seconds=max(last, 0.0),
    )


GUITAR_TRACKS = ("EasySingle", "MediumSingle", "HardSingle", "ExpertSingle")


def pick_track(text: str, requested: str = "auto") -> str:
    """Choose a guitar difficulty section. ``auto`` picks the first that exists."""
    if requested != "auto":
        if f"[{requested}]" not in text:
            raise ValueError(f"chart has no [{requested}]")
        return requested
    for name in GUITAR_TRACKS:
        if f"[{name}]" in text:
            return name
    raise ValueError("chart has no guitar track")


def load_chart(path: Path | str, track: str = "ExpertSingle") -> Chart:
    return parse_chart(Path(path).read_text(encoding="utf-8"), track=track)
