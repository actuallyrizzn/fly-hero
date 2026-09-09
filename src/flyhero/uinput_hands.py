"""Hands that can record a song, or press a real /dev/uinput guitar."""

from __future__ import annotations

from flyhero.guitar import GuitarMap, KeyEvent, diff_action
from flyhero.types import Action


class RecordingHands:
    """No kernel device. The Phase 3 visual route lives here."""

    def __init__(self, mapping: GuitarMap | None = None) -> None:
        self.mapping = mapping or GuitarMap()
        self.events: list[KeyEvent] = []
        self.last = Action.idle()
        self.t_seconds = 0.0
        self.calls = 0
        self.song_actions: list[Action] = []

    def set_time(self, t_seconds: float) -> None:
        self.t_seconds = t_seconds

    def apply(self, action: Action) -> None:
        self.calls += 1
        for code, down in diff_action(self.last, action, self.mapping):
            self.events.append(
                KeyEvent(t_seconds=self.t_seconds, key=self.mapping.name(code), down=down)
            )
        self.last = action

    def render(self) -> str:
        return "\n".join(event.render() for event in self.events)


class DeviceHands:
    """Write EV_KEY edges to an injected device (real UInput or a fake)."""

    def __init__(self, device, mapping: GuitarMap | None = None) -> None:
        if device is None:
            raise ValueError("device is required")
        self.device = device
        self.mapping = mapping or GuitarMap()
        self.last = Action.idle()
        self.calls = 0

    def apply(self, action: Action) -> None:
        from flyhero.guitar import EV_KEY, EV_SYN, SYN_REPORT

        self.calls += 1
        edges = diff_action(self.last, action, self.mapping)
        for code, down in edges:
            self.device.write(EV_KEY, code, 1 if down else 0)
        if edges:
            self.device.syn() if hasattr(self.device, "syn") else self.device.write(
                EV_SYN, SYN_REPORT, 0
            )
        self.last = action


def open_uinput(mapping: GuitarMap | None = None, factory=None):
    """Open a virtual keyboard. `factory` is for tests; live uses evdev."""
    mapping = mapping or GuitarMap()
    codes = list(mapping.fret_codes) + [mapping.strum_code]
    if factory is not None:
        return factory(codes)
    try:
        from evdev import UInput, ecodes
    except ImportError as exc:  # pragma: no cover - CI has no evdev
        raise RuntimeError("live guitar needs evdev (pip install evdev)") from exc
    cap = {ecodes.EV_KEY: codes}
    return UInput(cap, name="Fly Hero guitar")
