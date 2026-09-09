"""Host and slice-gate constants."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

COVERAGE_FLOOR = 90

DEFAULT_CLONEHERO_BIN = Path.home() / "Games" / "clonehero" / "clonehero"
DEFAULT_SONGS_DIR = Path.home() / ".clonehero" / "Songs"
DEFAULT_UINPUT = Path("/dev/uinput")


@dataclass(frozen=True)
class HostConfig:
    """Where Clone Hero and the virtual guitar live on this machine."""

    clonehero_bin: Path = DEFAULT_CLONEHERO_BIN
    songs_dir: Path = DEFAULT_SONGS_DIR
    uinput_path: Path = DEFAULT_UINPUT
    display: str | None = None

    def clonehero_present(self) -> bool:
        return self.clonehero_bin.is_file() and self.clonehero_bin.stat().st_mode & 0o111 != 0

    def uinput_present(self) -> bool:
        return self.uinput_path.exists()

    def songs_dir_present(self) -> bool:
        return self.songs_dir.is_dir()

    def desktop_ready(self) -> bool:
        return self.clonehero_present() and self.uinput_present()

    @classmethod
    def ngram_defaults(cls, display: str | None = ":0") -> HostConfig:
        return cls(display=display)
