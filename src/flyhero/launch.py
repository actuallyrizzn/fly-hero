"""Start Clone Hero on a song. Otto does not play; the fly does.

Clone Hero's ``--song --player Guitar,Easy`` path is a *bot preview*.
The PRD forbids that bot as the fly. The harness only passes ``--song``
so the highway comes up for a real controller (uinput).
"""

from __future__ import annotations

from pathlib import Path

from flyhero.config import HostConfig

DEFAULT_FIRST_SONG = (
    Path.home()
    / ".clonehero"
    / "Songs"
    / "Thingerthing"
    / "Covers & vGH's"
    / "Kazotsky Kick vGH"
)

INSTRUMENTS = (
    "Guitar",
    "Bass",
    "Rhythm",
    "GuitarCoop",
    "Keys",
    "Drums",
    "ProDrums",
)
DIFFICULTIES = ("Easy", "Medium", "Hard", "Expert")


class BotPreviewForbidden(RuntimeError):
    """Raised if someone tries to launch Clone Hero's practice bot as the fly."""


def song_folder(path: Path | str) -> Path:
    """``--song`` wants the song directory, not ``notes.chart``."""
    folder = Path(path)
    if folder.suffix.lower() in {".chart", ".mid"}:
        return folder.parent
    return folder


def load_song_argv(
    song: Path | str,
    *,
    config: HostConfig | None = None,
    width: int = 1280,
    height: int = 720,
    fullscreen: bool = False,
) -> list[str]:
    """Argv that opens a song folder. Never adds ``--player`` (that is the bot)."""
    host = config or HostConfig()
    if width < 1 or height < 1:
        raise ValueError("window size must be positive")
    folder = song_folder(song)
    argv = [
        str(host.clonehero_bin),
        "-screen-fullscreen",
        "1" if fullscreen else "0",
        "-screen-width",
        str(width),
        "-screen-height",
        str(height),
        "--song",
        str(folder),
    ]
    reject_bot_preview(argv)
    return argv


def reject_bot_preview(argv: list[str] | tuple[str, ...]) -> None:
    """The official ``--player`` flag starts Clone Hero's bot, not Fly Hero."""
    tokens = [part.lower() for part in argv]
    if "--player" in tokens or "-p" in tokens:
        raise BotPreviewForbidden(
            "Clone Hero --player is the chart-preview bot. It is not the fly."
        )


def bot_preview_argv(
    song: Path | str,
    *,
    instrument: str = "Guitar",
    difficulty: str = "Easy",
    config: HostConfig | None = None,
) -> list[str]:
    """Documented only so tests can refuse it. Do not call from play_live."""
    if instrument not in INSTRUMENTS:
        raise ValueError(f"unknown instrument {instrument}")
    if difficulty not in DIFFICULTIES:
        raise ValueError(f"unknown difficulty {difficulty}")
    _ = config
    raise BotPreviewForbidden(
        f"refusing bot preview {instrument},{difficulty} on {song_folder(song)}"
    )


def start_clonehero(argv: list[str] | tuple[str, ...], runner=None):
    """Spawn Clone Hero. Tests inject ``runner``; live uses Popen."""
    command = list(argv)
    reject_bot_preview(command)
    if runner is None:
        import subprocess

        runner = subprocess.Popen
    return runner(command)
