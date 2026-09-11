"""Clone Hero's own word: ``~/.clonehero/scorestats.json`` after each play."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path

DEFAULT_PATH = Path.home() / ".clonehero" / "scorestats.json"


@dataclass(frozen=True)
class GameResult:
    song_name: str
    difficulty: str
    notes_hit: int
    total_notes: int
    score: int
    max_streak: int
    excess_hits: int
    timestamp: str
    modifiers: tuple[str, ...]

    @property
    def accuracy(self) -> float:
        return self.notes_hit / self.total_notes if self.total_notes else 0.0


def parse_scorestats(text: str) -> GameResult:
    data = json.loads(text)
    players = data.get("players") or []
    if not players:
        raise ValueError("scorestats has no players")
    player = players[0]
    return GameResult(
        song_name=str(data.get("song_name", "")),
        difficulty=str(player.get("difficulty", "")),
        notes_hit=int(player.get("notes_hit", 0)),
        total_notes=int(player.get("total_notes", 0)),
        score=int(player.get("score", 0)),
        max_streak=int(player.get("max_streak", 0)),
        excess_hits=int(player.get("excess_hits", 0)),
        timestamp=str(data.get("score_timestamp", "")),
        modifiers=tuple(str(m) for m in player.get("modifiers", [])),
    )


def read_scorestats(path: Path | None = None) -> GameResult | None:
    target = path or DEFAULT_PATH
    if not target.is_file():
        return None
    return parse_scorestats(target.read_text(encoding="utf-8"))


def wait_for_new_result(
    previous: str | None,
    *,
    path: Path | None = None,
    timeout: float = 15.0,
    poll: float = 0.5,
    clock=None,
    sleeper=None,
) -> GameResult | None:
    """Block until the game writes a result newer than ``previous`` (a timestamp)."""
    now = clock or time.monotonic
    pause = sleeper or time.sleep
    started = now()
    while True:
        try:
            result = read_scorestats(path)
        except (ValueError, json.JSONDecodeError):
            result = None  # half-written file; try again
        if result is not None and result.timestamp != (previous or ""):
            return result
        if now() - started >= timeout:
            return None
        pause(poll)
