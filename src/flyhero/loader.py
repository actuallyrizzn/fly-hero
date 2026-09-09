"""Walk Clone Hero menus until the highway. One classified frame → one action.

``--song`` without ``--player`` errors ("No players were loaded").
``--player`` is Clone Hero's chart-preview bot — forbidden as the fly.
So the harness joins as Guest and picks the song itself.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from PIL import Image

from flyhero.detect import is_highway

SCREENS = (
    "loading",
    "error_cli",
    "title",
    "profile",
    "update",
    "main",
    "songs",
    "instrument",
    "difficulty",
    "modifiers",
    "ready",
    "highway",
    "unknown",
)
SETUP = frozenset({"instrument", "difficulty", "modifiers", "ready"})
MAX_STEPS = 24
UNKNOWN_LIMIT = 4
DEFAULT_QUERY = "kazotsky"
TEMPLATE_SIZE = (160, 90)
TEMPLATE_DIR = Path(__file__).resolve().parent / "screens"


class UnknownScreen(RuntimeError):
    """Frame matched nothing. Stop instead of mashing keys."""


class LoaderStuck(RuntimeError):
    """Highway never appeared within the step budget."""


@dataclass
class LoaderState:
    setup_steps: int = 0
    unknown_streak: int = 0
    seen: list[str] = field(default_factory=list)


def _rgb(image: Image.Image) -> Image.Image:
    return image.convert("RGB").resize(TEMPLATE_SIZE, Image.Resampling.BILINEAR)


def _pixels(image: Image.Image) -> list[tuple[int, int, int]]:
    rgb = image.convert("RGB")
    width, height = rgb.size
    pix = rgb.load()
    return [pix[x, y] for y in range(height) for x in range(width)]


def _mean_luma(image: Image.Image) -> float:
    pixels = _pixels(_rgb(image))
    total = 0.0
    for red, green, blue in pixels:
        total += 0.3 * red + 0.59 * green + 0.11 * blue
    return total / len(pixels)


def _box_luma(image: Image.Image, box: tuple[int, int, int, int]) -> float:
    pixels = _pixels(_rgb(image).crop(box))
    total = 0.0
    for red, green, blue in pixels:
        total += 0.3 * red + 0.59 * green + 0.11 * blue
    return total / len(pixels)


def _white_count(
    image: Image.Image,
    box: tuple[int, int, int, int],
    floor: int = 180,
) -> int:
    hits = 0
    for red, green, blue in _pixels(_rgb(image).crop(box)):
        if red >= floor and green >= floor and blue >= floor:
            hits += 1
    return hits


def guest_highlight(image: Image.Image) -> bool:
    """Profile screen: Guest row is a bright bar in the bottom-left."""
    return _white_count(image, (0, 62, 48, 90)) >= 40


def load_templates(directory: Path | None = None) -> dict[str, Image.Image]:
    folder = directory or TEMPLATE_DIR
    found: dict[str, Image.Image] = {}
    if not folder.is_dir():
        return found
    for path in folder.glob("*.png"):
        found[path.stem] = Image.open(path).convert("RGB")
    return found


def _thumb(image: Image.Image) -> bytes:
    return _rgb(image).resize((32, 18), Image.Resampling.BILINEAR).tobytes()


def _mse(left: bytes, right: bytes) -> float:
    return sum((a - b) ** 2 for a, b in zip(left, right)) / len(left)


def classify(
    image: Image.Image,
    *,
    templates: dict[str, Image.Image] | None = None,
    max_mse: float = 2500.0,
) -> str:
    """Name the screen. Fail closed to ``unknown`` rather than guess a key."""
    if is_highway(image):
        return "highway"
    luma = _mean_luma(image)
    mid = _box_luma(image, (50, 35, 110, 65))
    if luma < 22:
        return "error_cli" if mid > 30 else "loading"
    if guest_highlight(image):
        return "profile"
    catalog = templates if templates is not None else load_templates()
    if not catalog:
        return _classify_rules(image)
    probe = _thumb(image)
    ranked: list[tuple[float, str]] = []
    for name, sample in catalog.items():
        if name in {"highway", "error_cli", "profile"}:
            continue
        ranked.append((_mse(probe, _thumb(sample)), name))
    if not ranked:
        return _classify_rules(image)
    ranked.sort()
    best_mse, best = ranked[0]
    if best_mse > max_mse:
        return "unknown"
    return best


def _classify_rules(image: Image.Image) -> str:
    """When templates are missing (thin install), use luma buckets."""
    center = _box_luma(image, (55, 20, 105, 50))
    top_right = _box_luma(image, (110, 0, 160, 25))
    if center > 190:
        return "title"
    if center > 150:
        return "main"
    if center < 50:
        return "update"
    if top_right < 42:
        return "songs"
    if center > 82:
        return "instrument"
    if center > 74:
        return "difficulty"
    if center > 72:
        return "modifiers"
    return "ready"


def keys_for(
    screen: str,
    state: LoaderState,
    *,
    query: str = DEFAULT_QUERY,
) -> list[str] | None:
    """Keys for this frame. ``None`` means the highway is up."""
    if screen == "highway":
        return None
    if screen == "unknown":
        state.unknown_streak += 1
        if state.unknown_streak >= UNKNOWN_LIMIT:
            raise UnknownScreen(
                "Clone Hero screen was not recognized: "
                + " → ".join(state.seen[-8:] or ["unknown"])
            )
        return []
    state.unknown_streak = 0
    if screen == "loading":
        return []
    if screen == "error_cli":
        return ["a"]
    if screen == "title":
        return ["enter"]
    if screen == "profile":
        return ["a"]
    if screen == "update":
        return ["s"]
    if screen == "main":
        return ["a"]
    if screen == "songs":
        letters = [char for char in query.lower() if char.isalpha()]
        return ["k", *letters, "enter"]
    if screen in SETUP:
        index = state.setup_steps
        state.setup_steps += 1
        if index == 0:
            return ["a"]
        if index == 1:
            return ["down", "down", "down", "a"]
        return ["a"]
    raise UnknownScreen(f"no action for {screen}")


def load_until_highway(
    grab,
    press,
    *,
    query: str = DEFAULT_QUERY,
    max_steps: int = MAX_STEPS,
    settle: float = 0.0,
    templates: dict[str, Image.Image] | None = None,
    max_mse: float = 2500.0,
    sleeper=None,
    state: LoaderState | None = None,
) -> Image.Image:
    """Classify → tap → wait, until ``highway`` or fail."""
    if max_steps < 1:
        raise ValueError("max_steps must be at least 1")
    pause = sleeper or (lambda _delay: None)
    walk = state or LoaderState()
    last = None
    for _ in range(max_steps):
        frame = grab()
        last = frame
        screen = classify(frame, templates=templates, max_mse=max_mse)
        walk.seen.append(screen)
        print(f"loader: {screen}", flush=True)
        keys = keys_for(screen, walk, query=query)
        if keys is None:
            return frame
        for name in keys:
            press(name)
        if settle:
            pause(settle)
    raise LoaderStuck(
        f"highway not reached in {max_steps} steps: {' → '.join(walk.seen)}"
    )
