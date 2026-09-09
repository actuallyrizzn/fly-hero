"""Start Clone Hero. Otto does not play; the fly does.

Clone Hero's ``--song`` flag without ``--player`` errors
("No players were loaded"). ``--song --player`` is their chart-preview
bot. The PRD forbids that bot as the fly. Live start is windowed
Clone Hero with no song flags — ``flyhero.loader`` walks the menus.
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


def game_argv(
    *,
    config: HostConfig | None = None,
    width: int = 1280,
    height: int = 720,
    fullscreen: bool = False,
) -> list[str]:
    """Windowed Clone Hero. No ``--song``, no ``--player``."""
    host = config or HostConfig()
    if width < 1 or height < 1:
        raise ValueError("window size must be positive")
    argv = [
        str(host.clonehero_bin),
        "-screen-fullscreen",
        "1" if fullscreen else "0",
        "-screen-width",
        str(width),
        "-screen-height",
        str(height),
    ]
    reject_bot_preview(argv)
    return argv


def load_song_argv(
    song: Path | str,
    *,
    config: HostConfig | None = None,
    width: int = 1280,
    height: int = 720,
    fullscreen: bool = False,
) -> list[str]:
    """Documented ``--song`` argv. Live load does not use this — it errors."""
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


def stop_clonehero(*, name: str = "clonehero", runner=None) -> None:
    """Stop a leftover game so --song starts clean. Tests inject ``runner``."""
    if runner is None:
        import subprocess

        runner = subprocess.run
    runner(["pkill", "-x", name], check=False)
    runner(["pkill", "-9", "-x", name], check=False)


def start_clonehero(argv: list[str] | tuple[str, ...], runner=None):
    """Spawn Clone Hero. Tests inject ``runner``; live uses Popen."""
    command = list(argv)
    reject_bot_preview(command)
    if runner is None:
        import subprocess

        runner = subprocess.Popen
    return runner(command)
