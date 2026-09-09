from __future__ import annotations

from pathlib import Path

from flyhero.config import COVERAGE_FLOOR, HostConfig
from flyhero.desktop import current_display, probe
from flyhero import __version__


def test_coverage_floor_is_ninety():
    assert COVERAGE_FLOOR == 90
    assert __version__ == "0.1.0"


def test_current_display_reads_env():
    assert current_display({}) is None
    assert current_display({"DISPLAY": ""}) is None
    assert current_display({"DISPLAY": ":0"}) == ":0"


def test_host_config_missing_paths(tmp_path: Path):
    host = HostConfig(
        clonehero_bin=tmp_path / "missing",
        songs_dir=tmp_path / "no-songs",
        uinput_path=tmp_path / "no-uinput",
        display=None,
    )
    assert host.clonehero_present() is False
    assert host.uinput_present() is False
    assert host.songs_dir_present() is False
    assert host.desktop_ready() is False


def test_host_config_present_paths(tmp_path: Path):
    binary = tmp_path / "clonehero"
    binary.write_text("#!/bin/sh\n", encoding="utf-8")
    binary.chmod(0o755)
    songs = tmp_path / "Songs"
    songs.mkdir()
    uinput = tmp_path / "uinput"
    uinput.write_text("", encoding="utf-8")
    host = HostConfig(
        clonehero_bin=binary,
        songs_dir=songs,
        uinput_path=uinput,
        display=":0",
    )
    assert host.clonehero_present() is True
    assert host.uinput_present() is True
    assert host.songs_dir_present() is True
    assert host.desktop_ready() is True


def test_probe_ready_requires_display(tmp_path: Path):
    binary = tmp_path / "clonehero"
    binary.write_text("#!/bin/sh\n", encoding="utf-8")
    binary.chmod(0o755)
    uinput = tmp_path / "uinput"
    uinput.write_text("", encoding="utf-8")
    host = HostConfig(
        clonehero_bin=binary,
        songs_dir=tmp_path / "Songs",
        uinput_path=uinput,
        display=None,
    )
    report = probe(host, env={})
    assert report.clonehero is True
    assert report.uinput is True
    assert report.ready is False
    host_disp = HostConfig(
        clonehero_bin=binary,
        songs_dir=tmp_path / "Songs",
        uinput_path=uinput,
        display=":1",
    )
    assert probe(host_disp, env={}).ready is True


def test_ngram_defaults_set_display():
    host = HostConfig.ngram_defaults()
    assert host.display == ":0"
    assert host.clonehero_bin.name == "clonehero"


def test_probe_defaults_and_live_display():
    report = probe(None, env=None)
    assert report.display == current_display()
    assert isinstance(report.ready, bool)
    assert isinstance(report.clonehero, bool)
