# Fly Hero harness

Otto builds this. The readout plays. Nobody sits in Clone Hero teaching a human the menus.

## Who does what

| Actor | Job | Not their job |
|---|---|---|
| **Harness** | Load a song, capture frames, run the player, score the log | Guess keys from a screenshot |
| **Readout** | Hold frets and strum from a highway *picture* | Receive hit clocks |
| **Otto** | Write tests, keep the pipeline green, watch a demo | Play the song |

Clone Hero’s official `--song --player Guitar,Easy` path is their **chart-preview bot**. The PRD forbids that bot as the fly. The harness may pass `--song` only.

## One pipeline, two hosts

```
chart
  │
  ├─► 1. teach   ChartEye pictures → labels → fit readout
  ├─► 2. record  same player → key log (no /dev/uinput in CI)
  ├─► 3. score   log vs chart notes → accept / reject
  │
  └─► 4. live (ngram only)
         launch --song → wait until highway is visible → play_live
         → same scorer on the same kind of log
```

CI always runs 1–3 on `tests/fixtures/midtempo.chart`. The laptop is a *demo of the repo*, not a second training method.

## Stage 1 — Teach (offline)

1. Parse `notes.chart` for one guitar track (`EasySingle` on Kazotsky; `ExpertSingle` on the fixture).
2. `ChartEye` paints lanes × depth. Near is the strike line. The player never sees timestamps.
3. Labels are “what occupies the near bin” (`label_from_frame`). That is the features-only ceiling.
4. Fit a linear readout to those labels. Frozen fly `W` is Phase 4 — this stage still teaches *a* readout so the loop is real.
5. Persist nothing secret. Weights are numbers in a file if we snapshot them; CI refits every run.

Fail the slice if fixture accuracy after teach + record is below **1.0** (every fixture note has a matching fret+strum in the window).

## Stage 2 — Record

`record_chart` ticks the player and writes `KeyEvent` rows (`t key down/up`). That log is the Phase 3 visual route. CI never opens `/dev/uinput`.

## Stage 3 — Score

A note is a **hit** when, inside `[t − window, t + window]`, the matching fret is held **and** strum is held. Window is wide enough for the record step (0.25s on the fixture) and tighter on live (0.02s ticks).

`ScoreReport.accepted()` is the gate. Idle hands score 0. A perfect Near-bin / fitted readout on the fixture scores 1.0.

## Stage 4 — Live (ngram)

1. `probe()` — Clone Hero binary, `/dev/uinput`, `DISPLAY`.
2. `load_song_argv` — windowed Clone Hero + `--song <folder>`. **No `--player`.**
3. Start the process (injectable in tests).
4. Grab frames (Shell.Screencast). `is_highway` must go true before timeout. If it never does, fail — do not start pressing keys into a menu.
5. `play_live` with the **same** readout as Stage 1. ChartEye is the POC eye; `--pixels` swaps in `LivePixelEye`.
6. Score the recorded log. Stop Clone Hero.

If the highway never appears, the bug is the loader, not the fly. Fix the loader. Do not ydotool through Quickplay.

## Commands

```bash
# CI / teach + score (no game)
python tools/run_session.py --offline tests/fixtures/midtempo.chart

# ngram demo — only after probe is ready
python tools/run_session.py --live --track EasySingle \
  ~/.clonehero/Songs/Thingerthing/Covers\ &\ vGH\'s/Kazotsky\ Kick\ vGH/notes.chart
```

## Hard stops

- Do not use Clone Hero’s practice bot as the player.
- Do not train `W`.
- Do not feed hit times into the player.
- Do not navigate menus by hand to “help” a session.
- Do not put song audio in git.
