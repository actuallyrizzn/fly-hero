from __future__ import annotations

from pathlib import Path

import pytest
from PIL import Image

from flyhero.detect import paint_receptors
from flyhero.loader import (
    LoaderState,
    LoaderStuck,
    UnknownScreen,
    classify,
    keys_for,
    load_templates,
    load_until_highway,
)
from flyhero.menu import RecordingMenu, UnknownKey, key_code

SCREENS = Path(__file__).parent / "fixtures" / "screens"


def templates():
    return load_templates(SCREENS)


@pytest.mark.parametrize(
    "name",
    [
        "title",
        "profile",
        "update",
        "main",
        "songs",
        "instrument",
        "difficulty",
        "modifiers",
        "ready",
        "error_cli",
    ],
)
def test_labeled_fixtures_classify(name):
    image = Image.open(SCREENS / f"{name}.png")
    assert classify(image, templates=templates()) == name


def test_paint_receptors_is_highway():
    assert classify(paint_receptors(), templates=templates()) == "highway"


def test_black_fade_is_loading_not_error():
    assert classify(Image.new("RGB", (200, 160), (4, 4, 4))) == "loading"


def test_unknown_when_far_from_templates():
    noise = Image.new("RGB", (160, 90), (200, 40, 40))
    assert classify(noise, templates=templates(), max_mse=50) == "unknown"


def test_rules_without_templates():
    title = Image.open(SCREENS / "title.png")
    assert classify(title, templates={}) == "title"
    main = Image.open(SCREENS / "main.png")
    assert classify(main, templates={}) == "main"
    songs = Image.open(SCREENS / "songs.png")
    assert classify(songs, templates={}) == "songs"
    update = Image.open(SCREENS / "update.png")
    assert classify(update, templates={}) == "update"
    assert classify(Image.open(SCREENS / "instrument.png"), templates={}) == "instrument"
    assert classify(Image.open(SCREENS / "difficulty.png"), templates={}) == "difficulty"
    assert classify(Image.open(SCREENS / "ready.png"), templates={}) == "ready"


def test_templates_missing_dir_falls_back(tmp_path: Path):
    from flyhero.loader import load_templates

    missing = tmp_path / "nope"
    assert load_templates(missing) == {}
    only_skip = {"highway": Image.new("RGB", (16, 16), (8, 8, 8))}
    title = Image.open(SCREENS / "title.png")
    assert classify(title, templates=only_skip) == "title"


def test_profile_uses_guest_highlight_not_title():
    profile = Image.open(SCREENS / "profile.png")
    title = Image.open(SCREENS / "title.png")
    assert classify(profile, templates=templates()) == "profile"
    assert classify(title, templates=templates()) == "title"


def test_keys_for_menu_path():
    state = LoaderState()
    assert keys_for("title", state) == ["enter"]
    assert keys_for("profile", state) == ["a"]
    assert keys_for("update", state) == ["s"]
    assert keys_for("main", state) == ["a"]
    assert keys_for("songs", state, query="kaz") == ["k"]
    assert keys_for("songs", state, query="kaz") == ["type:kaz", "enter"]
    assert keys_for("songs", state, query="kaz") == ["a"]
    assert keys_for("songs", state, query="kaz") == []
    assert keys_for("loading", state) == []
    assert keys_for("highway", state) is None
    assert keys_for("error_cli", state) == ["a"]
    assert keys_for("instrument", state) == ["a"]
    assert keys_for("instrument", state) == []
    assert keys_for("difficulty", state) == ["down", "down", "down", "a"]
    assert keys_for("modifiers", state) == ["a"]
    assert keys_for("ready", state) == ["a"]
    assert keys_for("title", state) == ["enter"]
    assert keys_for("title", LoaderState(title_tries=4)) == []
    assert keys_for("profile", LoaderState(passed={"profile"})) == ["s"]
    assert keys_for("main", LoaderState(passed={"main"})) == []
    assert keys_for("unknown", LoaderState()) == []
    with pytest.raises(UnknownScreen, match="not recognized"):
        stuck = LoaderState(unknown_streak=3)
        keys_for("unknown", stuck)
    with pytest.raises(UnknownScreen, match="no action"):
        keys_for("nope", LoaderState())


def test_load_until_highway_walks_and_stops():
    frames = [
        Image.open(SCREENS / "title.png"),
        Image.open(SCREENS / "profile.png"),
        Image.open(SCREENS / "main.png"),
        Image.open(SCREENS / "songs.png"),
        Image.open(SCREENS / "songs.png"),
        Image.open(SCREENS / "songs.png"),
        Image.open(SCREENS / "instrument.png"),
        Image.open(SCREENS / "difficulty.png"),
        Image.open(SCREENS / "modifiers.png"),
        Image.open(SCREENS / "ready.png"),
        paint_receptors(),
    ]
    menu = RecordingMenu()

    def grab():
        return frames.pop(0)

    seen = load_until_highway(
        grab,
        menu.tap,
        query="kaz",
        settle=0.1,
        templates=templates(),
        sleeper=lambda delay: None,
        confirm=1,
    )
    assert classify(seen, templates=templates()) == "highway"
    assert menu.taps[0] == "enter"
    assert "k" in menu.taps
    assert menu.taps.count("down") == 3


def test_stale_highway_before_songs_is_ignored():
    menu = RecordingMenu()
    with pytest.raises(LoaderStuck, match="highway not reached"):
        load_until_highway(
            paint_receptors,
            menu.tap,
            max_steps=3,
            confirm=1,
            settle=0.0,
        )
    assert menu.taps == []


def test_load_until_highway_unknown_and_stuck():
    menu = RecordingMenu()
    red = Image.new("RGB", (160, 90), (200, 10, 10))
    with pytest.raises(UnknownScreen, match="not recognized"):
        load_until_highway(
            lambda: red,
            menu.tap,
            templates=templates(),
            max_steps=8,
            max_mse=10,
        )
    with pytest.raises(LoaderStuck, match="highway not reached"):
        load_until_highway(
            lambda: Image.open(SCREENS / "title.png"),
            menu.tap,
            templates=templates(),
            max_steps=1,
        )
    with pytest.raises(ValueError, match="max_steps"):
        load_until_highway(lambda: paint_receptors(), menu.tap, max_steps=0)


def test_menu_key_codes():
    assert key_code("enter") == 28
    assert key_code("k") == 37
    with pytest.raises(UnknownKey, match="no menu key"):
        key_code("f13")


def test_empty_template_dir_uses_rules(tmp_path: Path):
    from flyhero.loader import load_templates

    assert load_templates(tmp_path) == {}
    title = Image.open(SCREENS / "title.png")
    assert classify(title, templates={}) == "title"


def test_default_menu_is_ydotool():
    from flyhero.menu import YdotoolMenu, default_menu

    assert isinstance(default_menu(), YdotoolMenu)


def test_ydotool_menu_injects_runner():
    from flyhero.menu import YdotoolMenu

    seen = {}

    def runner(cmd, check=False, env=None):
        seen["cmd"] = cmd
        seen["env"] = env
        seen["check"] = check

    menu = YdotoolMenu(runner=runner, env={"YDOTOOL_SOCKET": "/tmp/.ydotool_socket"})
    menu.tap("enter")
    assert seen["cmd"][0] == "ydotool"
    assert "28:1" in seen["cmd"]
    assert seen["env"]["YDOTOOL_SOCKET"] == "/tmp/.ydotool_socket"
    menu.tap("type:kaz")
    assert seen["cmd"][:2] == ["ydotool", "type"]
    assert seen["cmd"][-1] == "kaz"
