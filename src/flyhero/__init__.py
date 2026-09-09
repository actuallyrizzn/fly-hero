"""Fly Hero — frozen fly reservoir plays Clone Hero."""

from flyhero.config import COVERAGE_FLOOR, HostConfig
from flyhero.hands import Hands, NullHands
from flyhero.player import Player
from flyhero.reservoir import NullReservoir, Reservoir
from flyhero.types import Action, FeatureFrame, Lane

__version__ = "0.1.0"

__all__ = [
    "Action",
    "COVERAGE_FLOOR",
    "FeatureFrame",
    "Hands",
    "HostConfig",
    "Lane",
    "NullHands",
    "NullReservoir",
    "Player",
    "Reservoir",
    "__version__",
]
