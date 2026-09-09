"""Highway picture as pixels — render for tests, decode for the fair eye.

Near is the *bottom* of the image (Clone Hero camera). Far is the top.
The player still only gets occupancies, not hit clocks.
"""

from __future__ import annotations

from dataclasses import dataclass

from PIL import Image, ImageDraw

from flyhero.types import DEFAULT_DEPTH, LANE_COUNT, FeatureFrame

# Guitar Hero / Clone Hero lane hues. Synthetic fixtures use these exact RGB
# values so decode is deterministic. Live capture uses the same centres with
# a looser distance so glow and lighting still classify.
LANE_RGB: tuple[tuple[int, int, int], ...] = (
    (36, 196, 72),  # green
    (220, 40, 44),  # red
    (228, 208, 36),  # yellow
    (48, 92, 228),  # blue
    (232, 132, 28),  # orange
)

HIGHWAY_RGB = (28, 24, 32)
OCCUPIED_THRESHOLD = 0.5
MAX_COLOR_DISTANCE = 95.0
LIVE_COLOR_DISTANCE = 140.0


@dataclass(frozen=True)
class HighwayRoi:
    """Crop of a screenshot, as fractions of width/height (0–1)."""

    left: float = 0.18
    top: float = 0.28
    right: float = 0.82
    bottom: float = 0.96

    def __post_init__(self) -> None:
        if not (0.0 <= self.left < self.right <= 1.0):
            raise ValueError("roi left/right must satisfy 0 <= left < right <= 1")
        if not (0.0 <= self.top < self.bottom <= 1.0):
            raise ValueError("roi top/bottom must satisfy 0 <= top < bottom <= 1")

    def crop(self, image: Image.Image) -> Image.Image:
        width, height = image.size
        box = (
            int(self.left * width),
            int(self.top * height),
            int(self.right * width),
            int(self.bottom * height),
        )
        return image.crop(box)


def _distance(pixel: tuple[int, ...], color: tuple[int, int, int]) -> float:
    return (
        (int(pixel[0]) - color[0]) ** 2
        + (int(pixel[1]) - color[1]) ** 2
        + (int(pixel[2]) - color[2]) ** 2
    ) ** 0.5


def classify_pixel(
    pixel: tuple[int, ...],
    *,
    max_distance: float = MAX_COLOR_DISTANCE,
) -> int | None:
    """Return a lane index or None if the pixel is highway / unknown."""
    if len(pixel) < 3:
        raise ValueError("pixel needs RGB")
    best_lane = None
    best = max_distance
    for lane, color in enumerate(LANE_RGB):
        dist = _distance(pixel, color)
        if dist < best:
            best = dist
            best_lane = lane
    return best_lane


def render_highway(
    frame: FeatureFrame,
    *,
    cell: int = 24,
    pad: int = 4,
) -> Image.Image:
    """Paint a lanes×depth grid. Occupied cells get that lane's gem color."""
    if cell < 4:
        raise ValueError("cell must be at least 4")
    width = LANE_COUNT * cell + pad * 2
    height = frame.depth * cell + pad * 2
    image = Image.new("RGB", (width, height), HIGHWAY_RGB)
    draw = ImageDraw.Draw(image)
    for lane, row in enumerate(frame.cells):
        for farness, value in enumerate(row):
            # farness 0 is near → bottom of the image
            row_from_top = frame.depth - 1 - farness
            x0 = pad + lane * cell + 2
            y0 = pad + row_from_top * cell + 2
            x1 = pad + (lane + 1) * cell - 3
            y1 = pad + (row_from_top + 1) * cell - 3
            color = LANE_RGB[lane] if value >= OCCUPIED_THRESHOLD else HIGHWAY_RGB
            draw.ellipse([x0, y0, x1, y1], fill=color)
    return image


def decode_highway(
    image: Image.Image,
    *,
    depth: int = DEFAULT_DEPTH,
    t_seconds: float = 0.0,
    roi: HighwayRoi | None = None,
    max_distance: float = MAX_COLOR_DISTANCE,
) -> FeatureFrame:
    """Turn a highway photo into the same FeatureFrame ChartEye produces."""
    if depth < 1:
        raise ValueError("depth must be at least 1")
    highway = image.convert("RGB")
    if roi is not None:
        highway = roi.crop(highway)
    width, height = highway.size
    if width < LANE_COUNT or height < depth:
        raise ValueError("image is too small to bin into lanes × depth")
    pixels = highway.load()
    rows = [[0.0] * depth for _ in range(LANE_COUNT)]
    for lane in range(LANE_COUNT):
        x0 = int(lane * width / LANE_COUNT)
        x1 = int((lane + 1) * width / LANE_COUNT)
        for farness in range(depth):
            row_from_top = depth - 1 - farness
            y0 = int(row_from_top * height / depth)
            y1 = int((row_from_top + 1) * height / depth)
            hits = 0
            total = 0
            for x in range(x0, max(x1, x0 + 1)):
                for y in range(y0, max(y1, y0 + 1)):
                    total += 1
                    if classify_pixel(pixels[x, y], max_distance=max_distance) == lane:
                        hits += 1
            if total and (hits / total) >= 0.08:
                rows[lane][farness] = 1.0
    return FeatureFrame.from_rows(rows, t_seconds=t_seconds)
