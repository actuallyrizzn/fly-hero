"""Menu keys. Guitar frets are not enough to walk Clone Hero's UI."""

from __future__ import annotations

import os
import subprocess

# Linux input-event-codes.h
KEY_ESC = 1
KEY_ENTER = 28
KEY_DOWN = 108
KEY_SPACE = 57
LETTER_CODES = {
    "a": 30,
    "b": 48,
    "c": 46,
    "d": 32,
    "e": 18,
    "f": 33,
    "g": 34,
    "h": 35,
    "i": 23,
    "j": 36,
    "k": 37,
    "l": 38,
    "m": 50,
    "n": 49,
    "o": 24,
    "p": 25,
    "q": 16,
    "r": 19,
    "s": 31,
    "t": 20,
    "u": 22,
    "v": 47,
    "w": 17,
    "x": 45,
    "y": 21,
    "z": 44,
}
NAMED_CODES = {
    "esc": KEY_ESC,
    "enter": KEY_ENTER,
    "down": KEY_DOWN,
    "space": KEY_SPACE,
    **LETTER_CODES,
}


class UnknownKey(ValueError):
    """Loader asked for a key we will not press."""


def key_code(name: str) -> int:
    token = name.lower()
    if token.startswith("type:"):
        raise UnknownKey("use tap() for type: payloads")
    if token not in NAMED_CODES:
        raise UnknownKey(f"no menu key {name}")
    return NAMED_CODES[token]


class RecordingMenu:
    """CI / tests: remember taps. No kernel, no ydotool."""

    def __init__(self) -> None:
        self.taps: list[str] = []

    def tap(self, name: str) -> None:
        token = name.lower()
        if token.startswith("type:"):
            self.taps.append(token)
            return
        key_code(token)
        self.taps.append(token)


class YdotoolMenu:
    """Press one key through ydotoold (ngram)."""

    def __init__(self, runner=None, env: dict[str, str] | None = None) -> None:
        self.runner = runner or subprocess.run
        self.env = env

    def tap(self, name: str) -> None:
        environ = os.environ.copy() if self.env is None else dict(self.env)
        environ.setdefault("YDOTOOL_SOCKET", "/tmp/.ydotool_socket")
        if name.lower().startswith("type:"):
            text = name.split(":", 1)[1]
            self.runner(
                ["ydotool", "type", "--key-delay", "80", "--", text],
                check=False,
                env=environ,
            )
            return
        code = key_code(name)
        self.runner(
            ["ydotool", "key", f"{code}:1", f"{code}:0"],
            check=False,
            env=environ,
        )


def default_menu():
    """Live default. Tests inject RecordingMenu."""
    return YdotoolMenu()
