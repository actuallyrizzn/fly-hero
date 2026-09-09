"""One tick: eye → reservoir → readout → hands."""

from __future__ import annotations

from flyhero.eye import Eye
from flyhero.hands import Hands
from flyhero.readout import Readout
from flyhero.reservoir import Reservoir
from flyhero.types import Action


class Player:
    def __init__(
        self,
        eye: Eye,
        reservoir: Reservoir,
        readout: Readout,
        hands: Hands,
    ) -> None:
        self.eye = eye
        self.reservoir = reservoir
        self.readout = readout
        self.hands = hands

    def reset(self) -> None:
        self.reservoir.reset()

    def tick(self, t_seconds: float) -> Action:
        frame = self.eye.see(t_seconds)
        state = self.reservoir.step(frame.as_vector())
        action = self.readout.act(state)
        self.hands.apply(action)
        return action
