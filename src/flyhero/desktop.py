"""Probe the ngram desktop without requiring it in CI."""

from __future__ import annotations

import os
from dataclasses import dataclass

from flyhero.config import HostConfig


@dataclass(frozen=True)
class DesktopReport:
    display: str | None
    clonehero: bool
    uinput: bool
    songs: bool
    ready: bool


def current_display(env: dict[str, str] | None = None) -> str | None:
    source = env if env is not None else os.environ
    value = source.get("DISPLAY")
    return value if value else None


def probe(config: HostConfig | None = None, env: dict[str, str] | None = None) -> DesktopReport:
    host = config or HostConfig()
    display = host.display if host.display is not None else current_display(env)
    clonehero = host.clonehero_present()
    uinput = host.uinput_present()
    songs = host.songs_dir_present()
    ready = clonehero and uinput and display is not None
    return DesktopReport(
        display=display,
        clonehero=clonehero,
        uinput=uinput,
        songs=songs,
        ready=ready,
    )
