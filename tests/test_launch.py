from __future__ import annotations

from pathlib import Path

import pytest

from flyhero.config import HostConfig
from flyhero.launch import (
    DEFAULT_FIRST_SONG,
    BotPreviewForbidden,
    bot_preview_argv,
    game_argv,
    load_song_argv,
    reject_bot_preview,
    song_folder,
    start_clonehero,
    stop_clonehero,
)


def test_song_folder_from_chart_and_dir(tmp_path: Path):
    folder = tmp_path / "Kazotsky Kick vGH"
    folder.mkdir()
    chart = folder / "notes.chart"
    chart.write_text("[Song]\n", encoding="utf-8")
    assert song_folder(chart) == folder
    assert song_folder(folder) == folder
    assert song_folder(folder / "notes.mid") == folder


def test_game_argv_windowed_no_song(tmp_path: Path):
    binary = tmp_path / "clonehero"
    binary.write_text("#!/bin/sh\n", encoding="utf-8")
    binary.chmod(0o755)
    argv = game_argv(config=HostConfig(clonehero_bin=binary), width=1280, height=720)
    assert argv[0] == str(binary)
    assert "--song" not in argv
    assert "--player" not in argv
    assert argv[argv.index("-screen-fullscreen") + 1] == "0"
    with pytest.raises(ValueError, match="positive"):
        game_argv(config=HostConfig(clonehero_bin=binary), width=0, height=720)


def test_load_song_argv_windowed_no_bot(tmp_path: Path):
    binary = tmp_path / "clonehero"
    binary.write_text("#!/bin/sh\n", encoding="utf-8")
    binary.chmod(0o755)
    song = tmp_path / "song" / "notes.chart"
    song.parent.mkdir()
    song.write_text("x", encoding="utf-8")
    argv = load_song_argv(
        song,
        config=HostConfig(clonehero_bin=binary),
        width=1280,
        height=720,
    )
    assert argv[0] == str(binary)
    assert argv[argv.index("--song") + 1] == str(song.parent)
    assert "-screen-fullscreen" in argv
    assert argv[argv.index("-screen-fullscreen") + 1] == "0"
    assert "--player" not in argv
    assert "-p" not in argv
    reject_bot_preview(argv)


def test_load_song_argv_fullscreen_and_bad_size(tmp_path: Path):
    binary = tmp_path / "clonehero"
    binary.write_text("#!/bin/sh\n", encoding="utf-8")
    binary.chmod(0o755)
    host = HostConfig(clonehero_bin=binary)
    argv = load_song_argv(tmp_path / "tune", config=host, fullscreen=True, width=640, height=360)
    assert argv[argv.index("-screen-fullscreen") + 1] == "1"
    assert argv[argv.index("-screen-width") + 1] == "640"
    with pytest.raises(ValueError, match="positive"):
        load_song_argv(tmp_path / "tune", config=host, width=0, height=720)
    with pytest.raises(ValueError, match="positive"):
        load_song_argv(tmp_path / "tune", config=host, width=1280, height=0)


def test_reject_bot_preview_flags():
    with pytest.raises(BotPreviewForbidden, match="not the fly"):
        reject_bot_preview(["clonehero", "--player", "Guitar,Easy"])
    with pytest.raises(BotPreviewForbidden, match="not the fly"):
        reject_bot_preview(["clonehero", "-p", "Guitar,Easy"])
    reject_bot_preview(["clonehero", "--song", "/tmp/tune"])


def test_bot_preview_argv_is_forbidden(tmp_path: Path):
    with pytest.raises(BotPreviewForbidden, match="refusing bot preview"):
        bot_preview_argv(tmp_path / "tune", instrument="Guitar", difficulty="Easy")
    with pytest.raises(ValueError, match="instrument"):
        bot_preview_argv(tmp_path / "tune", instrument="Banjo")
    with pytest.raises(ValueError, match="difficulty"):
        bot_preview_argv(tmp_path / "tune", difficulty="Insane")


def test_default_first_song_is_kazotsky():
    assert DEFAULT_FIRST_SONG.name == "Kazotsky Kick vGH"
    assert "Thingerthing" in DEFAULT_FIRST_SONG.parts


def test_load_song_argv_uses_host_default_binary():
    argv = load_song_argv(DEFAULT_FIRST_SONG)
    assert argv[0].endswith("clonehero")
    assert argv[argv.index("--song") + 1] == str(DEFAULT_FIRST_SONG)


def test_start_clonehero_injects_runner_and_blocks_bot():
    seen = {}

    def runner(command):
        seen["command"] = command
        return "ok"

    argv = load_song_argv(DEFAULT_FIRST_SONG)
    assert start_clonehero(argv, runner=runner) == "ok"
    assert seen["command"][0].endswith("clonehero")
    with pytest.raises(BotPreviewForbidden):
        start_clonehero(["clonehero", "--player", "Guitar,Easy"], runner=runner)


def test_stop_clonehero_pkills():
    seen = {}

    def runner(cmd, check=False):
        seen["cmd"] = cmd
        seen["check"] = check

    stop_clonehero(runner=runner)
    assert seen["cmd"] == ["pkill", "-x", "clonehero"]
    assert seen["check"] is False


def test_stop_clonehero_uses_run(monkeypatch):
    import subprocess

    monkeypatch.setattr(subprocess, "run", lambda cmd, check=False: ("run", cmd, check))
    assert stop_clonehero() is None


def test_start_clonehero_uses_popen(monkeypatch):
    import subprocess

    monkeypatch.setattr(subprocess, "Popen", lambda cmd: ("popen", cmd))
    argv = load_song_argv(DEFAULT_FIRST_SONG)
    assert start_clonehero(argv)[0] == "popen"
