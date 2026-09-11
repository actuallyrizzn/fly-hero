"""Append-only JSONL event log for Fly Cast (and other listeners)."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any


class EventWriter:
    """Write one JSON object per line. Safe no-op when path is None."""

    def __init__(self, path: Path | None) -> None:
        self.path = path
        self._prev_frets: tuple[bool, ...] | None = None
        self._prev_strum = False
        if path is not None:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("", encoding="utf-8")

    @property
    def enabled(self) -> bool:
        return self.path is not None

    def emit(self, cue: str, **fields: Any) -> None:
        if self.path is None:
            return
        row = {"t": time.time(), "cue": cue.upper(), **fields}
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(row, separators=(",", ":")) + "\n")

    def song_start(self, *, song: str = "", track: str = "") -> None:
        self.emit("SONG_START", song=song, track=track)

    def song_end(self) -> None:
        self.emit("SONG_END")

    def score(
        self,
        *,
        hits: int,
        notes: int,
        score: int,
        max_streak: int,
        accuracy: float,
    ) -> None:
        pct = int(round(100.0 * accuracy)) if notes else 0
        self.emit(
            "SCORE",
            hits=hits,
            notes=notes,
            score=score,
            max_streak=max_streak,
            accuracy=accuracy,
            detail=f"{pct}%",
        )

    def action_edges(self, frets: tuple[bool, ...] | list[bool], strum: bool) -> None:
        """Emit HIT-ish fret/strum edges (coarse — not Clone Hero hit detection)."""
        ft = tuple(bool(x) for x in frets)
        if self._prev_frets is None:
            self._prev_frets = ft
            self._prev_strum = strum
            return
        lanes = ("LANE_G", "LANE_R", "LANE_Y", "LANE_B", "LANE_O")
        for i, name in enumerate(lanes):
            if i < len(ft) and ft[i] and not self._prev_frets[i]:
                self.emit(name)
                self.emit("HIT", detail=name)
        if strum and not self._prev_strum:
            self.emit("HIT", detail="STRUM")
        self._prev_frets = ft
        self._prev_strum = strum
