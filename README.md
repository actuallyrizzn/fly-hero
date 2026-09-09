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

## Phase 0 (this commit)

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
