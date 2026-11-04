# Praxion demo film — script and edit (final, 2026-11-04)

Final film: `artifacts/demo/film/praxion_demo.mp4`, 1920×1080, 30 fps, 2:59.5, H.264 + AAC. Built by `demo/film/assemble.py` from the rendered scenes in `demo/film/scenes/` (see `demo/film/README.md`). Every number spoken or shown is listed with its source in `demo/film/SPEC.md`; the hardware numbers come from `docs/HARDWARE_RESULTS.md`, which is generated from the run bundles.

What is real and what is not: all dashboard shots are replays of recorded runs; all board footage is the phone recording of the filmed fan session on 2026-11-03 (fan on at 22:17:06 and 22:37:16 EST, matching `board_verification.json`); the terminal shot is the live readout of that session. Two backgrounds are generated clips (a pump room, a data-centre aisle) and carry the on-screen label "background: illustration"; they illustrate the problem and the next application and are never used as evidence. The trace in the problem diagram is labelled "illustration" as well.

## Edit (segment · starts at · length · what is on screen)

| # | start | length | shot | narration |
|---|---|---|---|---|
| 1 | 0:00 | 9.0 s | Meta theme lines over the dimmed pump-room background | N1 |
| 2 | 0:08.6 | 5.0 s | phone footage, punched in: a hand switches the fan on | N1 |
| 3 | 0:13.2 | 3.5 s | phone footage: the live terminal readout, temperature falling, heater rising | — |
| 4 | 0:16.8 | 5.0 s | title card PRAXION + three tags | N2 |
| 5 | 0:21.4 | 26.0 s | problem diagram: controller tuned once, machine drifts, trace leaves the band | N3 |
| 6 | 0:46.9 | 30.0 s | the loop: eight steps across three trust zones | N4 |
| 7 | 1:16.5 | 8.0 s | dashboard replay, simulated tank, run v13-s11 (REPLAY badge visible) | N4 |
| 8 | 1:24.1 | 6.0 s | stat card: 90.6 % less post-change error | N5 |
| 9 | 1:29.7 | 6.0 s | card: a $50 heater board, nothing changed but the driver | N6 |
| 10 | 1:35.3 | 5.0 s | photo of the rig, slow push-in | N6 |
| 11 | 1:39.4 | 6.0 s | phone footage, wide: fan switched on | N6 |
| 12 | 1:45.0 | 6.0 s | phone footage: handheld approach to the board | N6 |
| 13 | 1:50.6 | 6.0 s | phone footage: board close-up, heater LED | N6 |
| 14 | 1:56.2 | 5.0 s | dashboard still: board A/B panel for hw2 | N6 |
| 15 | 2:00.8 | 12.0 s | bars: 8.99 °C vs 3.77 °C, 0 % → 53 % in band, −58 %, heater 46 % vs 76 % | N7 |
| 16 | 2:12.4 | 22.0 s | results: 7/10, 8/8, 7/7, 4/7, and 4/4 board wins (58, 75, 66, 34 %), zero safety events, 3 failures kept | N8 |
| 17 | 2:33.9 | 4.0 s | the four board A/B tables stacked | N8 |
| 18 | 2:37.5 | 22.0 s | close over the dimmed data-centre background: honesty lines, the theme quote, wordmark, repo | N9 |

Cross-dissolves of 0.4 s between segments. Music bed at −16 dB under the voice, 1.5 s fade in, 4 s fade out. Integrated loudness −14.4 LUFS. Two lines (N4, N8) are time-stretched 4–5 % to fit their beats.

## Narration (Seed Audio TTS, preset voice "Arthur", chosen by ear from four samples; every number is on screen in the same beat)

- **N1 (0:01)** Last night, at ten seventeen, we broke a machine on purpose. By ten forty-five, an AI had repaired it, and we had measured the repair on the machine itself.
- **N2 (0:17)** This is Praxion. An AI control engineer.
- **N3 (0:23)** Every machine that holds something steady runs on a small piece of code called a controller. An engineer writes it once, after studying the machine. Then the machine drifts. A heater weakens, a pump wears, a filter clogs. The controller keeps yesterday's recipe, and nobody comes back to re-learn the machine.
- **N4 (0:47)** Give Praxion a machine it has never seen. A Meta Muse model designs small, safe experiments, and a trusted supervisor checks each one first. From the data, Muse writes the controller itself, as Python you can read. The code runs in a sealed sandbox and is scored on hidden scenarios the model never sees. When the machine changes, a trusted monitor notices. Muse re-identifies the machine, names what changed, and writes a repair, promoted only if it beats the frozen original on the same hidden tests.
- **N5 (1:24)** In simulation, on this tank, the repair cut the post-change error by ninety percent.
- **N6 (1:32)** Then the real thing: a fifty-dollar heater board. Nothing in the agent changed, only the driver. Muse learned the board in thirty minutes, and its first controller passed. We switched a fan on. The monitor caught it within a minute. Muse diagnosed increased heat loss and rewrote its controller. Then we did what most demos skip: we ran the old controller and the repaired one on the physical board, under the same fan.
- **N7 (2:01)** The old one gave up at forty-six percent power and slid to thirty-four degrees. The repair pushed to seventy-six, and climbed back. Fifty-eight percent less error, measured on the board.
- **N8 (2:13)** One run is a story, so we ran it ten times, eight of them unattended overnight with a trusted fault at the heater. The monitor fired every time. The diagnosis was right seven of seven. The gate accepted a repair in four of seven attempts, and all four beat the original on the board, with zero safety interventions. The three that were not good enough are in the results too.
- **N9 (2:44)** What it is not: a controller for any machine, or a safety guarantee. Every claim lives in a hashed bundle an audit script can replay. Praxion. The engineer who comes back.

## Numbers used, with sources

| spoken / shown | source |
|---|---|
| 22:17, 22:45 (fan on, session complete) | `artifacts/runs/hw2-20261103-074537-698ba8/event_log.jsonl`, `board_verification.json` |
| 90.6 % less post-change error, 5/5 scenarios, zero violations | run `v13-s11-20261031-020922-a0e68e`, `docs/BENCHMARKS.md`, README |
| $50 board, 45 °C target, ±1.5 °C band, 30 min discovery, monitor within a minute (66 s), diagnosis "heat loss increased" | README "Real hardware", `docs/HARDWARE_RESULTS.md` |
| 8.99 °C vs 3.77 °C, 0 % → 53 % in band, −58 %, heater 46 % vs 76 %, 34 °C | `artifacts/runs/hw2-…/board_verification.json`, fan-session terminal log |
| 10 runs; 7/10; 8/8; 7/7; 4/7; 4/4 (58, 75, 66, 34 %); 0 overrides or violations in 11 board trials; 3 attempts with no acceptable repair | `docs/HARDWARE_RESULTS.md` Summary and per-run table |

## Rules kept

Nothing shown happened only in a model; where a model's forecast appears (dashed lines in the board panel) it sits next to the measurement. REPLAY badges stay visible in dashboard shots. Generated backgrounds are labelled. No "any machine", no "guaranteed safe", no "beats PID".
