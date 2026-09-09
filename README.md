# Fly Hero

A GitHub repository — not a weekend script — for a frozen fruit-fly wiring graph that plays [Clone Hero](https://clonehero.net/) by *seeing* the note highway.

Dev box: **ngram** (Lenovo IdeaPad Slim 3, Ubuntu desktop). The laptop screen is where we watch it. This repo is what we keep.

Tasks: [Fly Hero board](https://tasks.decisionsciencecorp.com/admin/projects.php?id=62) · PRD [Doc #1292](https://tasks.decisionsciencecorp.com/admin/doc.php?id=1292)

## Locked

- **Fair eye:** pixels of the live Clone Hero window.
- **POC / fallback eye:** highway encoded from the chart as a picture (lanes × depth). Not hit timestamps.
- **Audio-only:** out.
- **`W`:** frozen. Only the readout trains.
- **Controls:** fly graph vs scrambled vs features-only.
- **Slice gate:** ≥90% unit + integration + that slice’s visual end-to-end routes, then commit and push.

## Phase 3 — play

`RecordingHands` turns a chart (or pixel frames) into a fret/strum key log. Clone Hero on ngram should bind guitar to **1–5** and **Down**. Live `DeviceHands` writes those edges to `/dev/uinput`. CI never opens the kernel device.

```bash
pytest tests/test_play.py
```

Family charts install on the laptop only: `~/.clonehero/Songs/Thingerthing`. First song: *Thinger's Warmup* (Easy/Medium if the chart has it).

## Phase 2 — fair eye (pixels)

`PixelEye` turns a highway photograph into the same lanes×depth frame as `ChartEye`. Tests paint a mid-tempo fixture and decode it back — that recorded PNG is the visual route. Live Clone Hero on ngram uses `LivePixelEye` + `grab_clonehero()` (Xwayland `xwininfo` + a screen grab). Same player; swap the eye.

```bash
pytest tests/test_pixel_eye.py
```

## Phase 1 — POC eye

`ChartEye` turns a `notes.chart` into the same lane×depth picture a player sees. Near is the strike line. The player does not get hit clocks. `NearBinReadout` is the features-only ceiling (copy the near bin). A later fly readout has to match or beat that.

```bash
pytest
```

Visual golden: `tests/test_chart_eye.py` renders the mid-tempo fixture as ASCII (`G|..#.|` …).

## Phase 0 — harness

Interfaces and a player loop with test doubles. Clone Hero install and `/dev/uinput` are *probed*, not required, so CI can stay green before the game is on disk.

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -e '.[dev]'
pytest
```

Coverage fails the build under 90%.

On ngram, after Clone Hero is unpacked to `~/Games/clonehero`:

```bash
DISPLAY=:0 python -c 'from flyhero.desktop import probe; print(probe())'
```

## Not this repo

Sanctum Tectum, Broca, Cerebellum, or Perc’s ngram entity lab. Those stay on their own boards.
