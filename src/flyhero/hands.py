"""Hands apply an Action to the world. Phase 0 does not open uinput."""

from __future__ import annotations

from typing import Protocol

from flyhero.types import Action


class Hands(Protocol):
    def apply(self, action: Action) -> None: ...


class NullHands:
    """Records the last action. Safe in CI and unit tests."""

    def __init__(self) -> None:
        self.last: Action | None = None
        self.calls = 0

    def apply(self, action: Action) -> None:
        self.last = action
        self.calls += 1
