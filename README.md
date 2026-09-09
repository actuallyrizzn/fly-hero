# Fly Hero

A GitHub repository — not a weekend script — for a frozen fruit-fly wiring graph that plays [Clone Hero](https://clonehero.net/) by *seeing* the note highway.

Dev box: **ngram** (Lenovo IdeaPad Slim 3, Ubuntu desktop). The laptop screen is where we watch it. This repo is what we keep.

Tasks: [Fly Hero board](https://tasks.decisionsciencecorp.com/admin/projects.php?id=62) · PRD [Doc #1292](https://tasks.decisionsciencecorp.com/admin/doc.php?id=1292)

Harness process (teach → record → score → live load): [docs/HARNESS.md](docs/HARNESS.md)

## Locked

- **Fair eye:** pixels of the live Clone Hero window.
- **POC / fallback eye:** highway encoded from the chart as a picture (lanes × depth). Not hit timestamps.
- **Audio-only:** out.
- **`W`:** frozen. Only the readout trains.
- **Controls:** fly graph vs scrambled vs features-only.
- **Slice gate:** ≥90% unit + integration + that slice’s visual end-to-end routes, then commit and push.

## Phase 3 — play

Otto builds the harness. The **fly readout** plays. Do not sit in Clone Hero menus teaching a human how to clear a song.

Clone Hero’s `--song` flag errors without a player, and `--player` is their **chart-preview bot** — that is not the fly (PRD). Live start is windowed Clone Hero; `flyhero.loader` classifies each frame and presses one key until the highway. The readout trains offline on highway pictures (`ChartEye` / pixels), then writes uinput.

`RecordingHands` turns a chart (or pixel frames) into a fret/strum key log. Live `DeviceHands` writes those edges to `/dev/uinput`. CI never opens the kernel device.

Repo / CI map is **1–5** and **Down**. Live Clone Hero on ngram uses the **stock keyboard**: **A S J K L** and **Down** (`--map clone-hero`, the default). Do not mix the two.

```bash
python tools/run_session.py --offline tests/fixtures/midtempo.chart --track ExpertSingle
pytest tests/test_play.py tests/test_score.py tests/test_session.py
# ngram: python tools/run_session.py --live --track EasySingle <notes.chart>
```

Family charts live on the laptop only: `~/.clonehero/Songs/Thingerthing`. First song: **Kazotsky Kick vGH**, Easy (36s, already on disk). Leave Clone Hero on stock keys, then:

```bash
python tools/play_live.py --pixels --track EasySingle \
  ~/.clonehero/Songs/Thingerthing/Covers\ &\ vGH\'s/Kazotsky\ Kick\ vGH/notes.chart
```

POC / no pixels (chart-as-picture eye): omit `--pixels`.

## Phase 2 — fair eye (pixels)

`PixelEye` turns a highway photograph into the same lanes×depth frame as `ChartEye`. Tests paint a mid-tempo fixture and decode it back — that recorded PNG is the visual route.

Live Clone Hero on ngram uses **GNOME Shell.Screencast** (clean 1920×1080 compositor frames) via `ScreenCastSession` + `grab_clonehero()`, then crops with `xwininfo` geometry. Raw `gst-launch pipewiresrc` on this box negotiates YUY2 and scrambles the picture — do not use that as the fair eye. X11 `ImageGrab` of Unity is black; kmsgrab of Intel CCS tiles is noise. Same player; swap the eye.

```bash
pytest tests/test_pixel_eye.py tests/test_pipewire.py
```

Prove one clean RGB frame on ngram (session bus + PipeWire, SSH as `rizzn`):

```bash
python tools/grab_frame.py -o /tmp/flyhero-vis/pipewire.png
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

The ngram venv must see Ubuntu’s `python3-dbus` and `python3-gi` (Mutter ScreenCast). After `python3 -m venv .venv`, set `include-system-site-packages = true` in `.venv/pyvenv.cfg`.

## Not this repo

Sanctum Tectum, Broca, Cerebellum, or Perc’s ngram entity lab. Those stay on their own boards.
