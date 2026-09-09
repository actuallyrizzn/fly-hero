"""POC eye: chart → highway picture. Fallback until pixels exist."""

from __future__ import annotations

from flyhero.chart import Chart
from flyhero.highway import encode_highway
from flyhero.types import DEFAULT_DEPTH, FeatureFrame


class ChartEye:
    def __init__(
        self,
        chart: Chart,
        *,
        look_ahead: float = 1.5,
        depth: int = DEFAULT_DEPTH,
    ) -> None:
        self.chart = chart
        self.look_ahead = look_ahead
        self.depth = depth

    def see(self, t_seconds: float) -> FeatureFrame:
        return encode_highway(
            self.chart,
            t_seconds,
            look_ahead=self.look_ahead,
            depth=self.depth,
        )
