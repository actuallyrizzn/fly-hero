"""One harness session: teach → record → score. Live is the same player."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from flyhero.chart import Chart, load_chart, pick_track
from flyhero.detect import wait_for_highway
from flyhero.guitar import GuitarMap
from flyhero.launch import game_argv, start_clonehero, stop_clonehero
from flyhero.loader import DEFAULT_QUERY, load_until_highway
from flyhero.live import play_live
from flyhero.play import record_chart
from flyhero.score import ScoreReport, score_log
from flyhero.train import LinearReadout, collect_samples, fit_linear_readout
from flyhero.types import DEFAULT_DEPTH
from flyhero.uinput_hands import RecordingHands


@dataclass(frozen=True)
class SessionResult:
    chart: Chart
    track: str
    log: RecordingHands
    score: ScoreReport
    readout: LinearReadout


def run_offline(
    chart: Chart,
    *,
    track: str = "ExpertSingle",
    step: float = 0.25,
    look_ahead: float = 1.0,
    depth: int = 4,
    window: float = 0.3,
    mapping: GuitarMap | None = None,
) -> SessionResult:
    """Teach a readout on ChartEye pictures, record keys, score. No game."""
    samples = collect_samples(chart, step=step, look_ahead=look_ahead, depth=depth)
    readout = fit_linear_readout(samples)
    log = RecordingHands(mapping or GuitarMap())
    record_chart(
        chart,
        step=step,
        look_ahead=look_ahead,
        depth=depth,
        readout=readout,
        hands=log,
    )
    return SessionResult(
        chart=chart,
        track=track,
        log=log,
        score=score_log(chart, log, window=window),
        readout=readout,
    )


def run_offline_path(
    path: Path | str,
    *,
    track: str = "auto",
    **kwargs,
) -> SessionResult:
    text = Path(path).read_text(encoding="utf-8")
    chosen = pick_track(text, track)
    chart = load_chart(path, track=chosen)
    return run_offline(chart, track=chosen, **kwargs)


def run_live(
    chart: Chart,
    hands,
    *,
    start=start_clonehero,
    grab=None,
    song: Path | str | None = None,
    countdown: float = 3.0,
    look_ahead: float = 1.5,
    depth: int = DEFAULT_DEPTH,
    step: float = 0.02,
    window: float = 0.12,
    readout: LinearReadout | None = None,
    argv: list[str] | None = None,
    waiter=wait_for_highway,
    stopper=None,
    clock=None,
    sleeper=None,
    eye=None,
    play=True,
) -> SessionResult:
    """Start the game, walk menus to the highway, play, score. Inject I/O in tests."""
    if grab is None:
        raise ValueError("live session needs a frame grabber")
    _ = song
    command = argv if argv is not None else game_argv()
    taught = readout
    mapping = getattr(hands, "mapping", None) or getattr(
        getattr(hands, "log", None), "mapping", None
    )
    if taught is None:
        taught = run_offline(
            chart,
            step=0.05,
            look_ahead=look_ahead,
            depth=depth,
            window=window,
            mapping=mapping,
        ).readout
    proc = start(command)
    try:
        waiter(grab)
        if play:
            play_live(
                chart,
                hands,
                eye=eye,
                readout=taught,
                look_ahead=look_ahead,
                depth=depth,
                step=step,
                countdown=countdown,
                clock=clock,
                sleeper=sleeper,
            )
    finally:
        if stopper is not None:
            stopper(proc)
        elif hasattr(proc, "terminate"):
            proc.terminate()
    log = hands.log if hasattr(hands, "log") else hands
    return SessionResult(
        chart=chart,
        track="",
        log=log,
        score=score_log(chart, log, window=window),
        readout=taught,
    )


def run_live_path(
    path: Path | str,
    *,
    track: str = "auto",
    countdown: float = 3.0,
    look_ahead: float = 1.5,
    depth: int = DEFAULT_DEPTH,
    step: float = 0.02,
    window: float = 0.12,
    play: bool = True,
    keep_game: bool = True,
    grab=None,
    start=None,
    stopper=None,
    killer=None,
    waiter=None,
    press=None,
    query: str = DEFAULT_QUERY,
    settle: float = 1.2,
    clock=None,
    sleeper=None,
    eye=None,
    hands=None,
    readout: LinearReadout | None = None,
    mapping: GuitarMap | None = None,
) -> SessionResult:
    """Ngram entry: stop leftover game, walk menus, play, score."""
    from flyhero.menu import default_menu
    from flyhero.shellcast import snapshot_frame

    text = Path(path).read_text(encoding="utf-8")
    chosen = pick_track(text, track)
    chart = load_chart(path, track=chosen)
    guitar = mapping or GuitarMap.clone_hero_keyboard()
    if hands is None:
        hands = RecordingHands(guitar)
    (killer or stop_clonehero)()
    tap = press if press is not None else default_menu().tap
    wait = waiter
    if wait is None:
        wait = lambda grabber: load_until_highway(
            grabber,
            tap,
            query=query,
            settle=settle,
            sleeper=sleeper,
        )
    argv = game_argv()
    result = run_live(
        chart,
        hands,
        start=start or start_clonehero,
        grab=grab or snapshot_frame,
        countdown=countdown,
        look_ahead=look_ahead,
        depth=depth,
        step=step,
        window=window,
        readout=readout,
        argv=argv,
        waiter=wait,
        stopper=stopper if stopper is not None else (lambda proc: None if keep_game else proc.terminate()),
        clock=clock,
        sleeper=sleeper,
        eye=eye,
        play=play,
    )
    return SessionResult(
        chart=result.chart,
        track=chosen,
        log=result.log,
        score=result.score,
        readout=result.readout,
    )
