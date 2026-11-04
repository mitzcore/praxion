# Praxion demo film — production spec (2026-11-04, final cut ≤ 3:00, 1920x1080 30 fps)

Audience: hackathon judges, technical and not. Register: calm, precise, confident; no hype words. Every number on screen comes from docs/HARDWARE_RESULTS.md, docs/BENCHMARKS.md or README.md and is listed in NUMBERS below. Nothing invented. Generated B-roll is labelled "illustration".

## Look
Dark UI world, same palette as the dashboard (scenes/film.css). Argument-diagram style: few elements, large type, one idea per screen, motion that explains (things light up in the order they happen). No stock-icon clutter, no gradients, no drop shadows. Easing: ease-out, 0.5–0.8 s. Text never smaller than 22 px at 1920 wide. Leave the bottom 140 px free for captions/subtitles (the edit may burn narration subtitles there). Every scene must look finished when paused at any second.

## Scene contract (for scripts/render: scratchpad/film/render/render_scenes.mjs)
- One HTML file per scene in scratchpad/film/scenes/, 1920x1080, `<title>` = file stem, `<link rel="stylesheet" href="film.css">`, `<script src="diagram.js">`, `<div id="stage">` containing everything plus two caption slots `<div id="cap0" class="cap"></div><div id="cap1" class="cap"></div>`.
- Drive all timing through `Diagram.run({name, duration, steps, tick})` from diagram.js (steps: {t,label,on,off,add,remove,caption,captionClass,fn}; tick(t) for continuous drawing). `?autoplay=1` plays and sets window.__done; `?t=12.5` renders a still at 12.5 s (use it to check layouts). No randomness, no Date.now in visuals, no external network (fonts are system fonts).
- Elements that appear later start with class `off` and get `on` in a step; use `data-anim` for the shared fade/transform transition. Counters/bars animate inside tick(t) from the step time.
- Durations below are fixed (the narration is cut to them). Hold the final state for the last 1.0 s of every scene.

## Scenes (narration in quotes is recorded separately; the scene must make sense silently)

01_quote — 9 s. Black. Three lines fade in one after another (t=0.5, 2.5, 4.5), large serif-less type, centred, max 2 lines each, ink colour:
  "Give a machine a new capability."
  "Unlock a better way to understand and control a physical system."
  "Show us what becomes possible when these models meet the real world."
  t=7.0 small label under them: "Meta Global AI Developer Hackathon 2026 · Push the Frontier". Hold.

01_title — 5 s. t=0.3 wordmark "PRAXION" (h1, letter-spacing 0.08em). t=1.4 subtitle "An AI control engineer that learns a machine, writes its own controller, and repairs it when the machine changes." (body, max width 1300). t=3.0 three small tags appear left→right: [green] MEASURED ON REAL HARDWARE · [blue] MUSE-AUTHORED CODE · [amber] FAILURES KEPT. Hold.

02_problem — 26 s. Argument diagram. Left: a machine glyph (simple heater/pump outline in SVG, 1 colour) with a controller box above it labelled "controller · tuned once by an engineer". Right: a live-drawing trace (tick) of a value holding inside a shaded band (green fill) — "in band". Steps:
  t=0.5 machine + controller appear; caption "Every machine that holds something steady runs on a small piece of code."
  t=5 trace starts drawing, holds in band.
  t=9 a label "months later" slides along a timeline under the trace; the machine glyph gets an amber "drift" mark (e.g. heater element dims / a pump icon gets a wear mark); caption "Then the machine drifts: a heater weakens, a pump wears, a filter clogs."
  t=14 the trace leaves the band and settles below it; band turns red-fill; caption "The controller keeps yesterday's recipe."
  t=19 the controller box gets a tag "unchanged since day one"; caption "Nobody comes back to re-learn the machine." Hold to 26.

03_loop — 30 s. The loop as an 8-node ring or left→right chain, grouped in three trust zones drawn as subtle background bands labelled (label class): UNTRUSTED — the model · SEMI-TRUSTED — sandbox · TRUSTED — supervisor, evaluator, monitor. Nodes (short labels, mono small sublabel): 1 Discover (bounded experiments) · 2 Write controller_v1.py · 3 Sandbox + hidden tests · 4 Deploy under supervisor · 5 Monitor fires · 6 Re-identify + diagnose · 7 Write controller_v2.py · 8 Re-gate, promote only if better. Light them in order, one per ~2.4 s from t=1, with a moving highlight on the connecting arrow; each node lit gets a one-line caption:
  1 "A Meta Muse model designs small, safe experiments; a trusted supervisor checks each one first."
  2 "From the data, Muse writes the controller itself. Python you can read."
  3 "That code runs in a sealed sandbox and is scored on hidden scenarios it never sees."
  4 "Only then is it deployed. Trusted code owns the actuator."
  5 "When the machine changes, a trusted monitor notices."
  6 "Muse re-identifies the machine and names what changed."
  7 "It writes a repair."
  8 "Promoted only if it beats the frozen original on the same hidden tests."
  t=22 the ring closes with a loop arrow and a label "repeat for the next change"; small tag under the sandbox node: "no network · read-only · non-root"; hold to 30.

03_simstat — 6 s. Stat card centred: label "SIMULATED TANK · RUN v13-s11"; big number counts up 0 → 90.6 % (num class, green) with the line "less post-change error after the repair"; sub-line (small): "same frozen hidden scenarios · 5 of 5 · zero safety violations". Source line: docs/BENCHMARKS.md. Hold.

04_hwintro — 6 s. Card: label "REAL HARDWARE"; h2 "A $50 heater board. Nothing changed but the driver."; body: "APMonitor TCLab · target 45 °C · band ±1.5 °C · 2026-11-03". Tag green "LIVE MUSE CALLS". Source line: docs/HARDWARE_RESULTS.md.

04_hwnumbers — 12 s. Title (h3): "Both controllers on the physical board, same fan, same 18 minutes". Two horizontal bars animate from 0 (tick): "frozen v1 — 8.99 °C average error after the change" (amber) and "repaired v2 — 3.77 °C" (green), scaled to the same axis; right of each bar the number counts up. Under them a second pair: "time in band after the change: 0 % → 53 %". t=8 a tag "−58 % · measured on the board, not a model" and small line "heater: v1 stopped at 46 % · v2 went to 76 %". Source line: artifacts/runs/hw2-20261103-074537-698ba8/board_verification.json.

05_results — 22 s. "Ten runs, unattended overnight." Left column counters count up one by one (t=1,3,5,7): "first controller passed the hidden tests 7 / 10", "change detected by the monitor 8 / 8", "diagnosis correct 7 / 7", "repair promoted by the gate 4 / 7". Right: t=9 four vertical bars grow (hw2 fan 58 %, hwb5 75 %, hwb7 66 %, hwb8 34 %) under the heading "promoted repairs that beat the original on the board: 4 / 4"; t=15 line "zero overrides or hard violations in 11 board trials"; t=17 small amber line "3 attempts produced no acceptable repair. They are in the results too." Source line: docs/HARDWARE_RESULTS.md (generated from the bundles).

06_close — 14 s. t=0.5 three short lines appear (one per 1.5 s), ink: "No fabricated evidence." "Failures kept." "Every claim replayable from a hashed bundle." t=6 they fade; the quote returns in muted: "Show us what becomes possible when these models meet the real world." t=9 wordmark PRAXION + line "the engineer who comes back" + mono "github.com/mitzcore/praxion" + small "built on Meta Muse · muse-spark-1.3 · Meta Model API". Hold.

## NUMBERS (sources)
90.6 % — run v13-s11, docs/BENCHMARKS.md / README "What happened in a real run". 5/5 scenarios, zero violations — same.
hw2 board: v1 8.99 °C / 0 % in band; v2 3.77 °C / 53 %; −58 %; heater 46 % vs 76 % — artifacts/runs/hw2-…/board_verification.json, docs/HARDWARE_RESULTS.md.
10 runs; G2 7/10; detected 8/8; diagnosis 7/7; promoted 4/7; board wins 4/4 (58, 75, 66, 34 %); 0 overrides/violations in 11 board trials — docs/HARDWARE_RESULTS.md Summary.
$50 board, TCLab, 45 °C, ±1.5 °C — README "Real hardware".

## Narration (recorded as separate lines; timings are targets)
N1 (over 01_quote→footage, 0:00–0:20): "Last night, at ten seventeen, we broke a machine on purpose. By ten forty-five, an AI had repaired it, and we had measured the repair on the machine itself."
N2 (01_title, 0:20–0:26): "This is Praxion. An AI control engineer."
N3 (02_problem, 0:26–0:52): "Every machine that holds something steady runs on a small piece of code called a controller. An engineer writes it once, after studying the machine. Then the machine drifts. A heater weakens, a pump wears, a filter clogs. The controller keeps yesterday's recipe, and nobody comes back to re-learn the machine."
N4 (03_loop, 0:52–1:22): "Give Praxion a machine it has never seen. A Meta Muse model designs small, safe experiments, and a trusted supervisor checks every one before it runs. From the data, Muse writes the controller itself, as Python you can read. That code runs in a sealed sandbox and is scored on hidden scenarios the model never sees. Only then is it deployed. When the machine changes, a trusted monitor notices, Muse re-identifies the machine, names what changed, and writes a repair. The repair is promoted only if it beats the frozen original on the same hidden tests."
N5 (03_simstat + tank replay, 1:22–1:30): "In simulation, on this tank, the repair cut the post-change error by ninety percent."
N6 (04 hardware footage, 1:30–2:05): "Then the real thing. A fifty-dollar heater board. Nothing in the agent changed, only the driver. Muse learned the board in thirty minutes and its first controller passed. We switched a fan on. The monitor caught it within a minute. Muse diagnosed increased heat loss and rewrote its controller. And then we did what most demos skip: we ran the old controller and the repaired one on the physical board, under the same fan."
N7 (04_hwnumbers, 2:05–2:20): "The old one gave up at forty-six percent power and slid to thirty-four degrees. The repair pushed to seventy-six and climbed back. Fifty-eight percent less error, measured on the board."
N8 (05_results, 2:20–2:44): "One run is a story, so we ran it ten times, eight of them unattended overnight with a trusted fault at the heater. The monitor fired every time. The diagnosis was right seven out of seven. The gate accepted a repair in four of seven attempts, and all four beat the original on the board, with zero safety interventions. The three that were not good enough are in the results too."
N9 (06_close, 2:44–3:00): "What it is not: a controller for any machine, or a safety guarantee. Every claim lives in a hashed bundle an audit script can replay. Praxion. The engineer who comes back."
