# Recording the demo video

`scripts/record_demo.py` records the dashboard replaying one stored run, following the segment plan
in `docs/DEMO_SCRIPT.md`. It drives the real UI in headless Chromium (Playwright). It only navigates,
scrolls, picks the replay speed, clicks Replay / Restart Replay and the controller tabs. It never
writes into the dashboard. The one page that is not the dashboard is the audit shot: the captured
stdout of `scripts/audit_run.py`, HTML-escaped and shown unchanged in a dark monospace page.

## Run it

```bash
uv sync
cd frontend && npm install && npx playwright install chromium && cd ..   # first time only
uv run python scripts/record_demo.py --run spark2-20261031-004636-3d012e
uv run python scripts/record_demo.py --run spark4-20261031-011710-0c4353 --out artifacts/demo/spark4
```

Options:

| Flag | Default | Meaning |
|---|---|---|
| `--run` | required | run id under `artifacts/runs/` (or `--root`) |
| `--out` | `artifacts/demo/<run_id>` | output directory (gitignored) |
| `--segments` | `default` | segment plan; only `default` (= `docs/DEMO_SCRIPT.md`) exists |
| `--speed-a` / `--speed-b` | `4` / `16` | pass A (discovery) and pass B (authoring onward) speeds from the script |
| `--max-length` | `230` | target footage in seconds. If the scripted speeds would exceed it, pass A speed is raised first, then pass B. The change is printed and stored in `segments.json` `speed_note`. |
| `--headful` | off | show the browser window |

If `frontend/dist` is missing it runs `npm install && npm run build`. If Playwright is missing it
installs the frontend devDependencies and Chromium.

## What it does

1. Runs `scripts/audit_run.py <run_id>` and saves the stdout as `audit.txt`.
2. Starts `uvicorn backend.main:app` on a free port with `PRAXION_ARTIFACT_ROOT` pointed at the runs.
3. Runs `scripts/record_demo.mjs`: a 1600×1000 viewport, dark color scheme, `recordVideo` on.
   - **Pass A** opens `/?run=<id>&replay=1&speed=4`, the same URL `scripts/replay_run.py` prints.
     Intro shot, then discovery: as each experiment result arrives the page scrolls smoothly between
     the Plant view (top) and the hypothesis ledger view (Plant head with its REPLAY badge stays at
     the top edge). The Timeline `follow` checkbox is checked and re-checked if it was cleared.
     The page waits for the `ready_to_generate` event and the GENERATING stage chip.
   - **Speed switch.** It picks `16x` in the replay speed select and clicks **Restart Replay**. The
     dashboard has no in-place speed change: Restart Replay re-emits the run from the first event.
     The stretch where pass B repeats discovery is recorded in `segments.json` as
     `passes.B.editor_cut`. Cut it in editing, as the script's two-pass plan says.
   - **Pass B**: scrolls to the Code panel when v1 is registered, to Evidence at the first
     evaluation, to the Plant and Trusted monitor at `monitoring_result`, and back to Code with the
     **v2** tab clicked (the diff) when v2 is registered. It waits for the replay to finish, then
     scrolls to the Adaptation block.
   - **Close-ups of the final state** (the panels stay on the final state after the pass ends):
     Code v1, held-out table, Plant, Trusted monitor, v1→v2 diff with Muse's diagnosis (and v2→v3 if
     present), each repair block, then the header with the REPLAY badge. Each is held for 3 to 4 s.
   - **Audit** last: the terminal render of `audit.txt`, scrolled to the `RESULT:` line.
4. Stops the server, measures the webm with `ffprobe`, and prints the files and video length.

## Output

```
artifacts/demo/<run_id>/
  demo.webm                         full recording (VP8, 1600x1000)
  s01_0m00s_intro.png               one or more screenshots per script segment:
  s02_0m15s_discovery.png           s<NN>_<script start time>_<title>[_<view>].png
  s03_0m50s_ready-to-generate.png
  s04_1m05s_authoring-and-g2_code-v1.png, ..._heldout.png
  s05_1m30s_monitoring_plant.png, ..._monitor.png
  s06_1m55s_adapting-diff_v1-v2-diff.png   (+ _v2-v3-diff.png when a v3 exists)
  s07_2m20s_final-adaptation_repair-v2.png (+ one per further repair block not already in frame)
  s09_2m50s_closing-header.png
  audit.png                         terminal render of audit_run.py stdout (segment 8)
  audit.txt                         the captured stdout itself
  segments.json                     offsets for voice-over alignment
```

### segments.json

All `*_s` values are seconds from the start of `demo.webm`. The recorder clock starts when the page
(and so the video) is created; skew against the file is usually under 0.3 s. `video_length_s` is the
ffprobe length; `recorder_clock_length_s` is the recorder's own clock.

- `passes.A`, `passes.B`: speed, start and end. `passes.B.editor_cut` is the repeated discovery.
- `speed_note`: set only when the scripted speeds were changed to stay under `--max-length`.
- `segments[]` in recording order. Each has `script_time`, `title`, `expect` (the script's
  "On screen" column), `live` (when the replay itself showed it), `closeup` (the held final-state
  view), `screenshots`, `observed` (text read from the page at that moment), and `issues` (what
  the UI did not show as the script expects).
- `script_numbers`: only for the script's run (`spark2-20261031-004636-3d012e`). The spoken
  numbers are checked against the page text. For any other run the script's numbers do not apply
  ([G3 branch]); narrate from `observed`.
- `recording_order` has the closing header (script 2:50) before the audit (script 2:40), because
  opening the audit page leaves the dashboard. Swap the two in editing.

## Known limits of the recording

- At 16x the authoring, G2, monitoring and adapting moments are seconds apart in the live replay.
  The narration for segments 4 to 7 should run over the close-ups, which is what the script intends.
- The header is not sticky. When the page is scrolled to the Code or Evidence panels the REPLAY
  badge is off screen. Every intro, discovery, readiness, plant and closing shot shows it. Cutting
  a close-up shot so the badge is in frame needs a sticky header in the frontend.
- The replay speed select offers 1x, 4x and 16x. Other pass B speeds are applied by reloading the
  replay URL with that speed, which the REPLAY badge then shows.
