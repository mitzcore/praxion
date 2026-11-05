# Praxion demo film — script and edit (final re-edit, 2026-11-04)

Final film: `artifacts/demo/film/praxion_demo_v2.mp4`, 1920×1080, 30 fps, 2:57.6, H.264 + AAC. Built by `demo/film/assemble.py` from the rendered scenes in `demo/film/scenes/` (see `demo/film/README.md`). Every number spoken or shown is listed with its source in `demo/film/SPEC.md`; the hardware numbers come from `docs/HARDWARE_RESULTS.md`, which is generated from the run bundles.

What is real and what is not: all dashboard shots are replays of recorded runs; all board footage is the phone recording of the filmed fan session on 2026-11-03 (fan on at 22:17:06 and 22:37:16 EST, matching `board_verification.json`); the terminal shot is the live readout of that session. Two backgrounds are generated clips (a pump room, a data-centre aisle, the latter used twice) and carry the on-screen label "background: illustration"; they illustrate the problem and the next application and are never used as evidence. The trace in the problem diagram is labelled "illustration" as well.

## Edit (segment · starts at · length · what is on screen)

| # | start | length | shot | narration |
|---|---|---|---|---|
| 1 | 0:00 | 6.6 s | hackathon theme lines over the dimmed pump-room background | music only |
| 2 | 0:06.2 | 15.0 s | the machines that run the world; controller performance survey bar | W |
| 3 | 0:20.8 | 18.0 s | what a repair looks like today; LBNL re-commissioning cost card | R |
| 4 | 0:38.4 | 4.0 s | title card PRAXION | L |
| 5 | 0:42.0 | 25.0 s | the loop across three trust zones | L |
| 6 | 1:06.6 | 20.0 s | data-centre facts and labelled arithmetic over the dimmed data-centre background | D |
| 7 | 1:26.2 | 15.0 s | server hall vs lab kit | B |
| 8–11 | 1:40.8 | 18.5 s | rig photo, fan switched on (wide), board close-up, board A/B panel for hw2 | H |
| 12 | 1:57.7 | 12.0 s | bars: 8.99 °C vs 3.77 °C, −58 % | N7 |
| 13 | 2:09.3 | 19.0 s | results: 7/10, 8/8, 7/7, 4/7, 4/4 board wins, zero safety events | N8 |
| 14–15 | 2:27.9 | 10.0 s | dashboard replay of simulated tank run v13-s11 (REPLAY badge); 90.6 % card | S |
| 16 | 2:37.1 | 20.5 s | close: "A heater board is small. The loop is not." wordmark, repo | C |

Cross-dissolves of 0.4 s. Music bed at −16 dB under the voice. Integrated loudness −14.7 LUFS. All narration time-stretched 10 % (atempo 1.1) to fit three minutes.

## Narration (Seed Audio TTS, preset voice "Arthur")

- **W** Refineries, power plants, water works, data centres: each is held steady by thousands of control loops, tuned once, by hand. In one Honeywell survey, only a third of them performed well.
- **R** When a machine drifts, a specialist comes on site, step-tests the live process, and retunes it, one loop at a time. Across hundreds of buildings, that work cut energy use by sixteen percent. But it takes skilled hours, so it is rarely done.
- **L** Praxion does that work itself. A Meta Muse model runs safe experiments, writes the controller as Python, and proves it on hidden tests in a sealed sandbox. When the machine changes, a monitor notices, and Muse writes a repair that ships only if it beats the original.
- **D** Take data centres. In twenty twenty-three, American data centres used four point four percent of the nation's electricity. The average site spends another fifty-six percent on overhead, mostly cooling. When DeepMind's models ran Google's cooling, that energy fell by forty percent.
- **B** Praxion has not run in a data centre. So we built the same problem at home: a fifty-dollar heater board, and a fan that changes its heat loss, like shifting airflow in a server hall.
- **H** Muse learned the board in thirty minutes. We switched the fan on, and the monitor caught it within a minute. Muse diagnosed increased heat loss and rewrote its controller. Then we ran the old one and the new one on the board, under the same fan.
- **N7** The old one gave up at forty-six percent power and slid to thirty-four degrees. The repair pushed to seventy-six, and climbed back. Fifty-eight percent less error, measured on the board.
- **N8** We ran it ten times, eight of them unattended overnight. The monitor fired every time, and the diagnosis was right seven of seven. Four repairs passed the gate, and all four beat the original on the board, with zero safety interventions.
- **S** Before the board, the same loop ran in simulation. On this tank, the best repair cut the post-change error by ninety percent.
- **C** A heater board is small. The loop is not. It is the same loop that holds server halls, reactors and water mains steady. This lab shows it works on real hardware. Next, bigger machines. Praxion. The engineer who comes back.

## Numbers used, with sources

| spoken / shown | source |
|---|---|
| controller performance 16 / 16 / 22 / 10 / 36 % (excellent, acceptable, fair, poor, open loop) | Honeywell installed-base survey (2000), reported in Control Engineering, "Performance monitoring and tuning controllers" |
| PID in 97 % of regulatory controllers, > 11,000 controllers | Desborough & Miller, "Increasing customer value of industrial control performance monitoring: Honeywell's experience", CPC-VI (2002) |
| re-commissioning: 643 buildings, median 16 % energy saved, $0.30/ft², 1.1-year payback | E. Mills, LBNL, "Building Commissioning: A Golden Opportunity for Reducing Energy Costs and Greenhouse-gas Emissions" (2009) |
| $30,000 for a 100,000 ft² building | arithmetic on the LBNL median, labelled on screen |
| US data centres 176 TWh, 4.4 % of US electricity, 2023 | LBNL, 2024 United States Data Center Energy Usage Report |
| average PUE 1.56 (56 % on top of IT load) | Uptime Institute, Global Data Center Survey 2024 |
| −40 % cooling energy, −15 % PUE overhead | Google / DeepMind blog, July 2016 |
| ≈ 9 TWh and ≈ $0.75 B a year | arithmetic: 176 × 0.56/1.56 × 0.15 at 8 ¢/kWh; labelled "Not a Praxion result" |
| 54 % of operators' last serious outage cost > $100,000 | Uptime Institute, Annual Outage Analysis 2024 |
| board and simulation numbers | as before: `docs/HARDWARE_RESULTS.md`, `artifacts/runs/hw2-…/board_verification.json`, run `v13-s11-20261031-020922-a0e68e`, `docs/BENCHMARKS.md` |

## Rules kept

Nothing shown happened only in a model; where a model's forecast appears (dashed lines in the board panel) it sits next to the measurement. REPLAY badges stay visible in dashboard shots. Generated backgrounds are labelled. No "any machine", no "guaranteed safe", no "beats PID".
