# Implementation status — Praxion

Living document. Updated by Claude at the end of every work block. A line moves to **Verified** only when the named command proves it.

_Last updated: 2026-11-01 — Phase 5 shipped to private repo; MVP-2 (physical TCLab heater) in progress for inclusion in the Nov 4 submission_

## MVP-2: physical plant (TCLab), started 2026-11-01

Decision (Mithran, Nov 1): buy the APMonitor TCLab ($49.99; arrives Nov 2) and include a real-hardware run in the Nov 4 submission. Plan: build and prove the whole path against the TCLab simulator today; run on the board Nov 2; film and docs Nov 3; Nov 4 buffer. Hardware demo is additive; MVP-1 ships regardless.

Design:
- `backend/profiles.py`: `PlantProfile` (dt, target/band, evaluation windows, exploration limits, envelope rate, safety limits, monitor thresholds, display units). `TANK` reproduces the frozen constants exactly; `TCLAB_SIM` / `TCLAB` use dt = 1 s, y = (T − 20)/60, target 45 °C, band ±1.5 °C, 900 s episodes, 180 s experiments (300 s after change), envelope 0.006/s, monitor window 60 s / hold 30 s / floor 0.02.
- Plants: `TCLabSim` (APMonitor TCLabModel, accelerated), `TCLabHardware` (USB serial), `ThermalTwin` (first-order-plus-dead-time, fitted by trusted code from the discovery experiments).
- Evaluation on a physical plant: hidden-scenario gates run on the fitted twin (`OrchestratorConfig(eval_plant_factory="twin")`); twin parameters are stored in the bundle and never enter the agent view. The operator applies the physical disturbance (foam over the sensor ≈ `actuator_lag`; fan ≈ `extra_leak`; heater 2 ≈ offset) when prompted at `monitor_pre_s`; the declared family selects the twin's disturbance suite for the same-scenario v1/v2 comparison.
- Prompts v1.4 (hash efaf4542800b0954): plant-agnostic wording; the envelope rate is read from the view rather than hardcoded. Tank benchmarks were recorded under v1.0–v1.3 and are unchanged.

**First live run on the TCLab simulator** (`artifacts/runs/tclabsim1-20261101-094639-2f0148`, Spark, prompt v1.4, $0.25, 9 calls): 8 experiments of 100–180 s (the v1.3 duration guidance carries over), holding power bracketed at u ≈ 0.45 for 44.8 °C; twin fit K = 60.5 °C, tau = 146 s, L = 15.8 s, no warnings; v1 G2 PASS on the twin, median MAE 0.0029 (≈0.17 °C), in-band 1.00. Monitor stayed quiet for 1500 s under a 20–40 s command delay: **a delay that is 20% of the time constant does not destabilize a gentle controller** (on the tank it was ≈60%). → Simulated `actuator_lag` default raised to 90–150 s for TCLab. **Second run** (`tclabsim2-20261101-095132-161001`): even a 90–150 s command delay produced no degradation in 1500 s; Muse's thermal controller is feed-forward (u ≈ 0.44) plus a small trim, which a delay cannot destabilize. Conclusion for the physical demo: on a slow thermal plant the disturbance that defeats a conservative controller is a **steady-state change** (fan = faster heat loss; weaker heater), where the feed-forward becomes wrong and a weak trim cannot recover within the band. Confirmed: **`tclabsim-weak-20261101-095646-62d477` (weaker heater, −25–40%) completed the full loop on the thermal plant**: monitor fired 91 s after the change; four re-identification experiments (drain to 21.6 °C, then steps at 0.5/0.7/0.65); diagnosis `actuator_weaker` correct; v2 promoted with post-change MAE 0.0108 → 0.0048 (5/5 improved, −56%), nominal kept. $1.51, 14 calls. The physical prop is a small USB fan aimed at the heater (extra loss) or, equivalently, the weaker-heater case.

## Current phase: 5 Ship (Phase 4 exit met)

Phase 4 exit: distribution under the frozen evaluator across 5 plant seeds measured for protocols v1.2 and v1.3; weakest links fixed or documented below. Remaining: benchmarks regeneration, README/DEMO numbers, video, public repo, submission.

## Verified

- **Full test tree green:** `uv run pytest -q` → 415 passed (incl. 28 Docker sandbox tests, 5 mock end-to-end orchestrator tests). `uv run ruff check backend tests scripts` clean.
- **Meta API live (2026-10-31):** `scripts/check_meta.py` → both `muse-spark-1.3` and `muse-wonder-1.0` reply; structured output with nested strict schemas verified on both; `reasoning_effort` accepted; reasoning tokens reported in usage.
- **Prompt v1.0 live:** `uv run pytest -q -m live` → both models return bounded, schema-valid first proposals with `ready_to_generate=false` on zero evidence.
- **Isolation:** 18 hostile candidates all contained in Docker with the static checker bypassed (network, file, fork, dunder/frame escapes, exec, memory bomb, CPU burn, infinite loop, huge/non-serializable state). Container probe confirms no network, read-only root, uid 65534, no capabilities, NoNewPrivs. `uv run pytest -q -m docker`.
- **Blindness:** `tests/test_agent_blindness.py` passes on synthetic sessions and on every snapshot of every recorded run under `artifacts/runs/`.
- **Frozen benchmark properties (plants 1–5 × scenarios 2000–2004):** default PID degrades under `actuator_lag`; `SLOW_PID_TUNING` recovers ≥70% in-band with zero violations; PID rejects all three offset families (monitor must not fire). `uv run pytest tests/test_baselines.py -s` prints the table.
- **Interlock:** with a worst-case controller under `actuator_lag`, true level peaks ≤ 0.908 (was 1.0 before). `tests/test_interlock.py`.
- **FIRST LIVE RUN** `artifacts/runs/spark-20261031-002956-c19d0d` (model `muse-spark-1.3`, plant seed 7, prompt v1.0):
  - 12 experiments proposed and run (E1 u=0.5, E2 u=0.9, E3 u=0 drain, … bracketing the equilibrium duty 0.57–0.59). Spark never declared readiness; exploration budget exhausted → GENERATING.
  - `controller_v1.py` (4890 bytes, sha256 04571db1…) authored by Muse: feed-forward map from observed equilibria + PI with setpoint weighting, measurement filter, conditional integration, anti-windup, rate limiting, own high-level guards. Machine card with measured rates and equilibria.
  - Static check ok; sandbox interface tests ok.
  - **G2 PASSED 10/10** held-out scenarios: median MAE 0.0080 (fixed PID 0.0077), in-band 1.00, zero overrides, zero violations.
  - Monitoring: degradation detected at t=198.2 s (disturbance at 60 s; window MAE 0.199 vs threshold 0.0508).
  - Run STOPPED at the 12-min wall clock before adaptation. Total model cost $0.498 (Spark, result.json), 14 calls (1 failed, retried), exploration latency 12→60 s per call as the view grew.

- **LIVE RUN #2** `artifacts/runs/spark2-20261031-004636-3d012e` (Spark, plant seed 7, prompt v1.0, full loop in 801 s ≈ 13 min, $0.70 per result.json):
  - Spark declared readiness after **8** experiments (vs budget-exhausted 12 in run #1).
  - v1 (2265 bytes): **G2 PASS 10/10, median MAE 0.0017** vs fixed PID 0.0077 (4.5× better tracking at equal energy).
  - Monitor fired at t=155.3 s (window MAE 0.39). Frozen v1 on the 300 s disturbance suite: post-change MAE 0.164, in-band 26%, 31 hard violations and 43 overrides (fixed PID: 0.160, 28 hard violations).
  - v2 and v3 authored with **correct diagnosis category `response_slower`** and a diagnosis that read the deadtime off the traces, but estimated it at 5–10 s (true ≈ 20 s). Both kept nominal G2 and both failed G3 (post-change MAE 0.168 / 0.204; 28 / 36 hard violations). **Gate 3: FAIL, honestly recorded.**
  - Independent audit `scripts/audit_run.py` PASS 7/7 (byte-identical authorship proof for v1–v3; no family name in any request).
- **Dashboard (agent D):** FastAPI + SSE + React; every value read from the bundle; replay at 1×/4×/16× reveals artifacts only as their events replay; verified against run #1 and the live run #2 with screenshots. `uv run pytest -q tests/test_api.py` 14 passed; `npm run build` 612 kB.
- **Benchmarks + audit tooling (agent E):** `scripts/run_evaluation.py` regenerates `docs/BENCHMARKS.md` with a content-addressed cache; `scripts/audit_run.py`; `scripts/export_artifacts.py`.

- **LIVE RUN #3** `artifacts/runs/spark3-20261031-010142-feac7f` (Spark, plant seed 7, **protocol v1.1**, 19 calls, $2.05, 1.26M input tokens):
  - v1: G2 PASS 10/10 (median MAE 0.0142, in-band 0.90). Monitor fired at 115.9 s. Frozen v1 post-change: MAE 0.193, in-band 0.15, 36 hard violations.
  - Re-identification: 4 experiments on the changed machine (E13–E16). The data showed the delay (u=0 at start of E15, level still rising 15 s later, falling only 6.8 s into E16 ≈ 22 s), but Muse measured delay within each experiment and reported 7–9 s.
  - v2: diagnosis `response_slower` (correct); post-change MAE 0.135 (5/5 improved, median −28.5%) but 7 hard violations and nominal in-band 0.43 → FAIL.
  - **v3: post-change MAE 0.0446 (5/5 improved, median −76.6%), 0 hard violations, 0 invalid, in-band 0.62. Meets every Gate 3 criterion on the changed machine.** Nominal (unchanged machine) in-band 0.21 → under the promotion rule the process was running (which also required nominal G2), the run recorded **FAILED** and v1 was retained. Under the current rule (decided while attempt 2 was running, before this result existed; see decisions log and event timestamps) v3 would be promoted. The run's recorded verdict stands as recorded.
  - Audit: to be run with the next benchmark regeneration.
- **LIVE RUN #4** `artifacts/runs/spark4-20261031-011710-0c4353` (Spark, plant seed 7, **protocol v1.2**, 18 calls, $1.65): v1 G2 PASS (MAE 0.0231, in-band 0.84). Monitor at 122.4 s. Re-identification: 40 s drain + two 15 s steps; Muse's justification: "Delay resolved to ~22–24 s by two direct measures (E12 u=0 break at 22.4 s, E14 u=0.5 onset at ~23 s)". True added delay 18–22 s + nominal 0.3–1 s. **v2 promoted on the first attempt: post-change MAE 0.0342 vs frozen v1 0.1831 (5/5 improved, median −81.5%), in-band 0.81, 0 hard violations.** Nominal after repair: in-band 0.07 (reported, not gated). Final stage COMPLETE.
- **LIVE RUN #5** `artifacts/runs/spark5-20261031-011712-e34d36` (Spark, **plant seed 11**, protocol v1.2, 16 calls, $1.36): v1 G2 PASS (MAE 0.0057, in-band 1.00). Monitor at 147.1 s. Both after-change drain proposals were refused by the supervisor at y ≥ 0.85 (bug: u=0 cannot raise the level; fixed, see decisions). Muse revised from the monitoring traces alone: **v2 promoted: 4/5 improved, median −23.8%, 0 hard violations; nominal G2 after repair also PASS.** Final stage COMPLETE.
- **LIVE RUN #8** `artifacts/runs/spark8-20261031-013049-bc09a1` (Spark, **plant seed 18**, protocol v1.2, 13 calls, $1.45, 680 s): readiness after 6 experiments; v1 G2 PASS (MAE 0.0035, in-band 0.98). Monitor at 177.2 s. Re-identification 40 s drain + three 14–16 s steps. **v2 promoted: 5/5 improved, median −72.4%, post-change in-band 0.87, 0 hard violations.** Nominal after repair: in-band 0.01 (reported).
- **PROTOCOL v1.3 BATCH** (`artifacts/runs/v13-s{3,7,11,14,18}-*`, Spark, `actuator_lag`, prompt hash 0d19650e641cac11), all five COMPLETE:

  | plant seed | discovery exps | v1 G2 (first candidate) | v1 post-change MAE / viol | repair | post-change MAE / in-band / viol | reduction | nominal kept | diagnosis | cost | time |
  |---|---|---|---|---|---|---|---|---|---|---|
  | 3 | 12 | PASS (in-band 0.89) | 0.186 / 21 | v3 (attempt 2) | 0.031 / 0.87 / 0 | −84% | no (0.36) | correct | $2.17 | 17 min |
  | 7 | 12 | PASS (0.78) | 0.190 / 7 | v2 | 0.095 / 0.32 / 0 | −50% | no (0.56) | correct | $1.71 | 11 min |
  | 11 | 12 | PASS (0.92) | 0.217 / 2 | v2 | 0.021 / 1.00 / 0 | −91% | yes (0.93) | correct | $1.75 | 11 min |
  | 14 | 11 | PASS (1.00) | 0.044 / 0 | v2 | 0.010 / 1.00 / 0 | −78% | yes (1.00) | correct | $1.72 | 14 min |
  | 18 | 12 | PASS (1.00) | 0.027 / 0 | v2 | 0.014 / 0.94 / 0 | −59% | yes (1.00) | correct | $1.71 | 17 min |

  **G1 5/5, G2 5/5 on the first candidate, G3 5/5, diagnosis 5/5, nominal kept 3/5.** Under v1.2 on the same machines: G2 4/5 (seed 3 never passed; seed 14 needed 4 candidates), G3 4/4 of deployed. Discovery experiments now include 15–20 s holds (v1.2: mostly 4–8 s).
- **LIVE RUN #7** `artifacts/runs/spark7-20261031-012959-a9c6d6` (Spark, **plant seed 14**, protocol v1.2, 21 calls, $4.30, 2.96M input tokens): v1–v3 failed G2 (in-band 0.35 / 0.19 / 0.42; same short-experiment equilibrium error as seed 3); v4 passed G2 (MAE 0.0094, in-band 1.00). Monitor at 165.2 s. Re-identification measured the delay at 24.1 s. **v5 promoted: 5/5 improved, median −77.6%, post-change MAE 0.0215, in-band 1.00, 0 hard violations; nominal G2 after repair PASS.** Final COMPLETE.
- **LIVE RUN #6** `artifacts/runs/spark6-20261031-012958-e01d87` (Spark, **plant seed 3**, protocol v1.2, 18 calls, $1.96): **FAILED at G2, 0/5 candidates.** Cause: 4–8 s experiments on a plant with deadband 0.17 never reached steady state; Muse estimated the equilibrium duty at 0.75 (true ≈ 0.58), the controller settled at 0.73 with its integral clamp exhausted at u = 0.62, and revisions did not extract the measured equilibrium from the traces. → Protocol v1.3.
- **Protocol v1.2 distribution (5 machines):** G2 reached on 4/5 (seed 3 failed; seed 14 needed 4 candidates); G3 passed on 4/4 deployed (median post-change MAE reductions −81.5%, −23.8%, −77.6%, −72.4%); diagnosis category correct 4/4; cost $1.36–$4.30 per run; 11–20 min per run.
- **Cost driver:** candidate evaluation traces (10 episodes × 150 points per candidate) dominate input tokens (up to 2.96M per run). A future view trim (traces for the worst 3 episodes, summaries for all) would cut this ~3×; not applied mid-batch.
- **Repairs are specific to the change they were written for** (from the regenerated benchmarks): under the offset families, the promoted repairs track worse than the original v1 did (e.g. `v13-s11` v2 under `pump_derate`: post-change MAE 0.1856, in-band 0.33, vs v1 0.0098). The repair detunes for a 24 s delay and loses the authority to absorb an offset quickly. A machine that reverts, or changes in a second way, would need another repair cycle. Stated in README limitations and SAFETY_LIMITATIONS.
- **Pattern across v1.2 repairs:** promoted controllers are much slower than needed on the original dynamics (nominal in-band 0.07 / 0.01 on seeds 7 / 18; seed 11 kept nominal G2). On the changed machine they reach in-band 0.81–0.87, below the hand-tuned slow PID (0.98, tuned post hoc on the same scenarios). Reported in BENCHMARKS; a possible v1.3 would ask for designs that stay acceptable if the delay shrinks back.
- **Protocol scorecard on plant seed 7 (same machine, same frozen scenarios, same model):** v1.0 → repairs −1% / −25% (worse), FAIL. v1.1 → −28% then −77%, criteria met on attempt 3. v1.2 → −81% on attempt 1. The controller, scores and seeds never changed; only what the agent was allowed to measure and told about its own actions.
- **WONDER RUN #1** `artifacts/runs/wonder1-20261031-010124-6130b3` (Wonder, plant seed 3, prompt v1.1): 6 sensible experiments, then STOPPED by the orchestrator's leak guard on a false positive (the word "hidden" in Muse's own ledger text). 9 calls, $2.24, 85k reasoning tokens; latency 17–93 s per call. Several `operator_note` fields contained unrelated hallucinated text ("lease log", ticket numbers) and two were empty; experiments themselves were coherent. Spark remains the primary demo model (coherent notes, 3–4× cheaper, strong v1 results).
- **Leak scanner redesigned** after that false positive: keys checked structurally (trusted names), values checked only for specific trusted identifiers, hidden-seed numbers checked everywhere except model-authored free text. Regression test with model English containing "hidden", "seed", "meta". All recorded runs re-audited: PASS.

## Observations that changed the design

- **PI controllers reject offset disturbances by construction** (agent A, Oct 31). Pump derate, extra leak, drain shift are all absorbed by the fixed PID with post-change MAE 0.0026–0.0055 across the five benchmark machines (`docs/BENCHMARKS.md`). → Added the dynamics-changing family `actuator_lag` (tau ×1.0–1.5 plus 18–22 s transport delay). Slowing the actuator alone does not break PI; only pure delay does. Offset families stay in the benchmark to show the monitor correctly *not* firing.
- **A 20 s command delay defeats a reactive y-based cutoff** (overflow to 1.0 on 34/500 plant×scenario combos). → Independent high-level interlock on true level (ideal float switch) + delay-line flush on trip. Documented in `docs/SAFETY_LIMITATIONS.md`.
- **Degradation under delay grows slowly.** At 180 s the live v1 looks fine (post-disturbance MAE 0.017); at 300 s it limit-cycles (0.086, 53% in-band, 5 interlock trips). → `DISTURBANCE_EPISODE_S` 180 → 300 (frozen before any official scoring). Monitored live rollout 300 s.
- **Detector calibration mid-settling inflates the baseline** (0.025 at 45 s). → calibrate on the window ending at 58 s.
- **Detector floor:** sweep over 25 lag / 75 offset / 75 nominal cases (agent C): floor 0.05 catches 24/25 with 0 false alarms; the safe band is only 0.0435–0.0494. Kept 0.05; margins documented. Detection latency 86–114 s is inherent to the delay.
- **Plant vs scenario split.** The evaluator tests "this machine on unseen scenarios" (same hidden parameters; different initial level, noise stream, disturbance magnitudes), not different machines. Cross-machine evidence comes from repeating the protocol over plant seeds in Phase 4.
- **Spark readiness.** With zero evidence both models correctly say not ready; with 12 experiments Spark still never declared readiness. Experiment efficiency is therefore budget-bound for Spark; to be compared with Wonder.

- **Repairs failed because the agent could not measure the changed machine.** Muse only saw post-change traces at 5 s resolution and never ran an experiment on the changed plant; it under-estimated the delay 2–4× and designed for it. → **Protocol v1.1:** after degradation, up to 4 bounded re-identification experiments on the changed machine (phase `after_change`) before revising; post-change evidence traces at 150 points; revision prompt asks for a quantified change. Prompt hash b24d8a294e0ba81e.
- **Adaptation-latency metric** returned 0 s for controllers that were briefly in band then limit-cycled. → Redefined as settling time (start of the final in-band run lasting to episode end), before any official scoring.

## Depth review — Phase 4 exit (protocols v1.0 → v1.3, 5 machines)

1. **Proved:** on five different hidden machines, with the same frozen evaluator, hidden scenarios, prompts and model, Praxion discovers the machine, authors a controller that passes the hidden-scenario gate on the first attempt, detects a hidden dynamics change, measures it, names the right category, and authors a repair that passes the changed-machine gate with zero safety violations (5/5). Every number regenerates from `scripts/run_evaluation.py`; every bundle passes `scripts/audit_run.py`.
2. **What a skeptic says:** "You iterated the protocol until it passed." Yes, four versions, each change logged with the measured failure that motivated it and each version's results kept (v1.0 FAIL, v1.1 criteria met on attempt 3, v1.2 4/5 G2, v1.3 5/5). Controllers, scores, seeds and gates were never tuned to a result; the one gate change (promotion rule) was made before any pass existed. "The repairs are slow controllers." Reported: nominal kept on 3/5; post-change in-band 0.32–1.00 vs hand-tuned slow PID 0.98. "Only Spark." Wonder was tried once (coherent experiments, hallucinated notes, stopped by our own guard); documented.
3. **Weakest link now:** seed 7's repair is the weakest (post-change in-band 0.32, −50%); and cost/latency are dominated by evaluation traces in the view (≈1M input tokens per run). Both are documented; neither is a correctness issue.
4. **Decision:** freeze protocol v1.3 for the submission. No further protocol changes before the video and repo are done.

## Depth review — Phase 4 iteration 1 (protocol v1.0 → v1.1 → v1.2)

1. **Proved:** letting the agent measure the changed machine turns the repair from "worse" (v1.0: −1%, −25%) into "better" (v1.1: −28% then −77% with zero violations). Same model, same machine, same frozen scenarios; only the protocol changed. Command: `uv run python scripts/run_live_demo.py --model muse-spark-1.3 --plant-seed 7`.
2. **What a skeptic says:** "The run says FAILED." Yes: the promotion rule in force required nominal G2 after repair; we changed the rule (changed-machine criteria only) before the passing result existed and logged it; the recorded verdict is not rewritten. "The repaired controller is sluggish on the original machine." True and reported; the machine that existed before the change no longer exists in the story. "N=1." Runs on seeds 7 and 11 under v1.2 are in flight; the Phase 4 batch follows.
3. **Weakest link:** the agent measured the delay from the start of each experiment rather than from the last command change, under-estimating it 2–3×. v1.2 gives the agent `command_before` and `seconds_since_command_last_changed_at_start` per experiment (facts about its own actions), says so in the prompt, and allows after-change holds up to 40 s under the same envelope.
4. **Cost:** input tokens per run rose to 1.26M with 150-point post-change traces; still $2 on Spark. Watch per-call context (max observed ≈ 150k).

## Depth review — Phase 2 exit (Gate 3 measured: FAIL under v1.0)

1. **Proved:** the full loop runs live end to end in 13 min: discovery, authoring, sandbox, hidden-scenario gate, deployment, trusted degradation detection, diagnosis, two revisions, same-scenario re-scoring, honest FAIL with v1 retained. Diagnosis category matched the hidden family both times.
2. **What a skeptic says:** "The repair did not work" — correct, and shown. "The disturbance is unfair" — a 20 s delay on a 30–45 s plant is severe but a slow PI provably recovers (0 trips, 0.018 MAE), so a solution exists. "You will now tune until it passes" — we change the *protocol* (let the agent measure the changed machine), never the controller, scores, or scenarios; every protocol version is logged with its hash and measured effect.
3. **Weakest link:** the agent's ability to quantify the change. Addressed by v1.1 re-identification; being measured now (runs spark3 seed 7, wonder1 seed 3).
4. **Secondary:** with a 20 s max experiment the response to a step only begins at the end of one experiment; the agent must chain two. If v1.1 still fails, consider a `hold` extension for after-change experiments at low duty within the envelope.

## Depth review — Phase 0 and Phase 1 exit

1. **Proved:** a real Muse model, blind to the plant, ran 12 self-chosen bounded experiments, wrote a controller that matches a hand-tuned PID on hidden scenarios, inside a sandbox proven against hostile code, with every view it saw stored and leak-checked. Command: `uv run python scripts/run_live_demo.py --model muse-spark-1.3 --plant-seed 7`.
2. **What a skeptic says:** (a) "A PI controller matching PID is not surprising" — true; the result is the *process*, and the honest comparison row is in the evidence. (b) "The disturbance was designed so PID fails" — true and documented: offset disturbances cannot test adaptation; the delay family is the legitimate case, and v1 fails it too (0.086 at 300 s). (c) "One run" — Phase 4 runs N ≥ 5 plant seeds.
3. **Weakest link:** the repair stage has not run live yet (wall clock). Fixed budget; re-running.
4. **Plan changes:** see decisions log.

## In progress

- **Verified 2026-11-01 03:30:** `uv run pytest -q -m "not live"` → 460 passed (Docker + slow included). `scripts/run_evaluation.py --sandbox docker` → `docs/BENCHMARKS.md` over 13 live runs (cross-run: v1.0 G3 0/2, v1.1 1/1, v1.2 4/5, v1.3 5/5). Demo recording `artifacts/demo/v13-s11-*/demo.webm` 2:55, segments.json, audit.png. README / DEMO_SCRIPT / PROVENANCE updated to v1.3 numbers; total live spend $25.27 over 14 runs.
- **Needs Mithran:** initial git commit (nothing committed yet), public GitHub repo `praxion`, voice-over on the replay video per docs/DEMO_SCRIPT.md, submission by Nov 4 6 PM ET. Protocol v1.3 batch on the same five seeds launched (`v13-s*`). Benchmarks regeneration running.
- Then: batch over plant seeds for the distribution (Phase 4), README/DEMO_SCRIPT, video, repo (Phase 5).

## Blocked

- None.

## Decisions log

- 2026-11-01: Protocol v1.3 (prompt hash 0d19650e641cac11): discovery prompt states the budget is counted in experiments not seconds and that equilibrium needs settled holds; authoring prompt warns that integral clamps tighter than the plausible feed-forward error guarantee a permanent offset; trusted `measured_summary` (start/end/last-tail mean of y and u, slope, measured in-band) per experiment and per evaluation episode, computed only from measured y and applied u; G2-failure feedback lists those facts. Reason: run spark6 (seed 3) failed G2 on all 5 candidates because 4–8 s experiments never reached steady state (equilibrium duty estimated 0.75 vs ≈0.58) and the integral clamp could not correct the offset; run spark7 (seed 14) needed 4 candidates for the same reason.
- 2026-11-01: MVP-2 on TCLab approved by Mithran for the Nov 4 submission; profiles module; twin-based gating for physical plants; prompts v1.4.
- 2026-11-01: Supervisor fix: a u=0 proposal is always approvable (bound == y cannot rise). Reason: run spark5 had both after-change drain proposals refused at y ≥ 0.85, blocking the safest action. Test added.
- 2026-11-01: Protocol v1.2 (prompt hash d9206efcefe117cb): per-experiment `command_before` and `seconds_since_command_last_changed_at_start`; prompt instructs measuring delay from the last command change; after-change experiments up to 40 s under the same worst-case envelope. Reason: run spark3 under-estimated a ≈22 s delay as 7–9 s by measuring within single experiments.
- 2026-11-01: **Gate 3 promotion rule**: judged on the changed machine only (≥3/5 scenarios with ≥20% post-change MAE reduction vs frozen v1, zero hard violations, zero invalid outputs). Nominal G2 after repair is re-scored and reported, not gated. Reason: the repaired controller is for the machine as it now is; requiring it to also pass on the machine that no longer exists is a robustness demand, not self-repair. Decided while no run had passed G3 (run spark3 v2: 5/5 improved by 28% median but 7 hard violations → still FAIL under the new rule). `max_adaptation_attempts` 2 → 3.
- 2026-11-01: Leak scanner: structural key check + specific identifiers + seed numbers outside model free text (reason: false positive on the word "hidden" stopped a $2.24 Wonder run). Orchestrator still refuses to send any view the scanner flags.
- 2026-11-01: Protocol v1.1 (re-identification experiments after degradation, 4 max; 150-point post-change traces). Reason: measured under-estimation of the delay in run #2 repairs.
- 2026-11-01: `adaptation_latency` redefined as settling time (frozen metric; changed before official scoring; reason: 0 s for limit-cycling controllers).
- 2026-11-01: Operator API exposes trusted data (disturbance family, hidden params in evaluation audit). Acceptable: the operator is not the agent; documented in README.

- 2026-10-31: `DISTURBANCE_EPISODE_S` 180 → 300 s (frozen config; changed before any official scoring because 180 s hides slowly growing delay-induced oscillation; measured v1: 0.017 → 0.086 MAE).
- 2026-10-31: Detector floor kept at 0.05 after sweep (24/25 lag detections, 0/150 false alarms). Monitor calibration window moved to [43, 58] s. Live monitored rollout 300 s, stop 40 s after detection.
- 2026-10-31: Wall-clock budget 12 → 30 min (measured need). Model-call budget 40 unchanged.
- 2026-10-31: Added `actuator_lag` family; `DISTURBANCE_FAMILIES` labels offset vs dynamics; added independent interlock; plant/scenario split; widened plant ranges with envelope rate 0.10.
- 2026-10-31: Diagnosis categories: actuator_weaker, outflow_increased, response_slower, sensor_changed, unknown; scored after the fact against the hidden family.
- 2026-10-31: Product name Praxion; Pi out; second plant stretch only; Fable reasons/validates, Opus implements.
- 2026-10-30: Stage-driven structured calls over free tool loop; Docker sandbox with dev-only subprocess fallback.
