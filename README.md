# Praxion

Praxion is an agent that is handed an unfamiliar simulated machine and has to learn to control it. A Meta Muse model (`muse-wonder-1.0` or `muse-spark-1.3`, called through the Meta Model API) designs bounded experiments, revises a hypothesis ledger from the measured responses, and writes an executable controller in Python. Trusted code checks that controller statically, runs it in a locked-down Docker sandbox, and scores it on hidden scenarios the model never sees. The controller is then deployed under a trusted safety runtime. When the machine's behavior changes, a trusted monitor detects the degradation. Muse then runs bounded experiments on the changed machine, names a diagnosis, and writes a revised controller. The revision is promoted only if it beats the frozen original on the same scenarios with zero safety violations. The plant is one simulated water tank family, tested on five hidden machines (plant seeds). Everything in this README happened in a recorded run, and every number names the bundle it came from.

Built for the Meta Global AI Developer Hackathon, Indie developer track.

**Demo video:** the script is [`docs/DEMO_SCRIPT.md`](docs/DEMO_SCRIPT.md). It is recorded from the real dashboard replaying run `v13-s11-20261031-020922-a0e68e` with `uv run python scripts/record_demo.py --run v13-s11-20261031-020922-a0e68e`. The output goes to `artifacts/demo/`, which is gitignored. The `.webm` is attached to the submission separately.

## What happened in a real run

Run `v13-s11-20261031-020922-a0e68e` (model `muse-spark-1.3`, plant seed 11, protocol v1.3, Docker sandbox, disturbance family `actuator_lag`). Every number below is from `artifacts/runs/v13-s11-20261031-020922-a0e68e/`.

1. **Discovery.** Muse proposed and ran 12 experiments: constant pump duty from 0.0 to 0.7, held 3 to 20 s. Each one names the ledger uncertainty it targets and gives a safety argument the supervisor checks. Muse did not declare readiness. The 12-experiment budget ran out, and the orchestrator moved to authoring. (`result.json`, `event_log.jsonl`)
2. **Authoring.** Muse wrote `controller_v1.py` (2326 bytes, sha256 `686ea165e103e5ae…`). Static check and sandbox interface tests passed. (`controller_v1.meta.json`)
3. **Hidden-scenario gate (G2).** v1 passed 10/10 held-out scenarios: median MAE 0.0132, mean in-band 0.925, zero overrides, zero hard violations. The fixed PID baseline on the same 10 scenarios: median MAE 0.0080, in-band 1.00. On this machine, before the change, PID tracked better. (`evaluation_v1.json`)
4. **Change.** v1 ran under the trusted runtime. At t = 60.0 s the hidden plant changed: a transport delay was added to the actuator. The trusted monitor fired at t = 89.5 s, with a 15 s window MAE of 0.2635 against a threshold of 0.05 (calibrated baseline 0.0124). (`monitoring.json`)
5. **Frozen v1 under the change.** On the 5 frozen disturbance scenarios (300 s each), v1 had median post-change MAE 0.2172, mean in-band 0.11, 2 hard violations and 3 overrides. The fixed PID on the same scenarios: 0.164 and 28 hard violations. (`evaluation_disturbance_v1.json`)
6. **Re-identification.** Muse ran 4 bounded experiments on the changed machine (E13 to E16). E13 was recorded `invalid`: it started at level 0.893 and the supervisor overrode once. E14 to E16 completed. (`result.json`, `event_log.jsonl`)
7. **Diagnosis.** Category `response_slower`, which the trusted scorer marks correct for the hidden family. Muse's diagnosis text, verbatim from `controller_v2.meta.json`:

   > Same u now acts ~24 s later, gain/drain/noise unchanged. E14 u=0.5 for 16 s from 0 stays flat 0.0-0.01 slope -0.0002 vs E4 same u rose to 0.227 slope +0.0114. E15 continuation of same 0.5 stays flat until ~193.7 (~24.1 s after 169.6 step) then rises 0.02->0.139 slope +0.0162, matching discovery rise rate. E16 cut 0.5->0 at 201.6 keeps rising 0.136->0.333 peak at 224.0 (~22.4 s) then falls with slope -0.0116 matching discovery drain -0.0097. Discovery E2 rose within 0.2 s, so Td_old <1 s, Td_new ~24 s (+/-1 s). Noise <0.01 unchanged. Old controller therefore drives delay-induced limit cycle 0.03-0.89 period ~80 s with hard violations seen in monitoring after_change and post-change eval.

   The family adds an 18 to 22 s transport delay on top of a nominal 0.3 to 1 s (`docs/IMPLEMENTATION_STATUS.md`).
8. **Repair.** Muse wrote `controller_v2.py` (3650 bytes, sha256 `3db8d5814fc90455…`). Its rationale: "Detuned for ~24 s deadtime while keeping nominal stability: Kp 0.80->0.22, Ki 0.12->0.018 …" (`controller_v2.meta.json`).
9. **Gate 3 on the same frozen scenarios.** Post-change median MAE 0.0205 vs 0.2172 for frozen v1. 5/5 scenarios improved by 20% or more, median reduction 90.6%. In-band 1.00, zero hard violations, zero overrides. (`evaluation_disturbance_v2.json`, `adaptation_v2.json`)
10. **Nominal after repair.** Re-scored on the original held-out scenarios: G2 PASS 10/10, median MAE 0.0233, in-band 0.934. (`evaluation_v2.json`)
11. **Outcome.** Final stage `COMPLETE`, reason "v2 promoted (nominal G2 after repair: pass)". 18 model calls, $1.747 estimated, 688.8 s wall time. (`result.json`)

The independent audit of this bundle passes 7/7:

```bash
uv run python scripts/audit_run.py v13-s11-20261031-020922-a0e68e
```

This is the best of the five v1.3 runs. It is not the typical one. Seed 7's repair under v1.3 cut post-change MAE by 50%, but post-change in-band was only 0.32. Two of the five v1.3 repairs did not keep nominal G2. See the table below.

### How it got there: four protocol versions

The first full loop did not work. We changed the protocol four times, and we kept every version's results. The protocol is what the agent may measure, what it is shown about its own actions, and the prompts. Controllers, scores, scenario seeds and the frozen evaluator were never edited to fit a result. Each change is logged with the measured failure that motivated it and a new prompt hash (`docs/IMPLEMENTATION_STATUS.md` decisions log, `docs/PROVENANCE.md`).

**v1.0, run `spark2-20261031-004636-3d012e` (seed 7). Gate 3 FAILED.** v1 passed G2 10/10 (median MAE 0.0017 vs fixed PID 0.0077). The monitor fired at t = 155.3 s. Muse picked the right category (`response_slower`) twice, but it had only seen post-change traces. It estimated the delay at 5 to 10 s, against a true value of about 20 s. v2 and v3 failed Gate 3: post-change MAE 0.168 and 0.204 vs frozen v1 0.164, 0/5 improved, 28 and 36 hard violations. The run ended `FAILED` and kept v1. That failure is what led to v1.1. (`artifacts/runs/spark2-20261031-004636-3d012e/`, `docs/IMPLEMENTATION_STATUS.md`)

**Scorecard on plant seed 7** (same machine, same frozen scenarios, same model; source `docs/IMPLEMENTATION_STATUS.md` and each run's `adaptation_v*.json`):

| Protocol | Run | Repair attempts (median post-change MAE change vs frozen v1) | Result |
|---|---|---|---|
| v1.0 | `spark2-20261031-004636-3d012e` | −1%, −25% (both worse) | FAIL |
| v1.1 | `spark3-20261031-010142-feac7f` | −28.5% (7 hard violations), −76.6% (0 hard violations) | changed-machine criteria met on attempt 3; recorded FAILED under the rule then in force (see below) |
| v1.2 | `spark4-20261031-011710-0c4353` | −81.5% | promoted on attempt 1 |
| v1.3 | `v13-s7-20261031-020602-18f408` | −50% | promoted; post-change in-band 0.32; nominal not kept (0.56) |

**v1.2 vs v1.3 on the same five machines** (plant seeds 3, 7, 11, 14, 18; source `docs/IMPLEMENTATION_STATUS.md`):

| Protocol | G2 on deployed v1 | G3 | Diagnosis category correct | Nominal kept after repair |
|---|---|---|---|---|
| v1.2 | 4/5 (seed 3 never passed; seed 14 needed 4 candidates) | 4/4 of deployed | 4/4 | 2/4 (seeds 11 and 14 kept; seeds 7 and 18: nominal in-band 0.07 / 0.01) |
| v1.3 | 5/5 on the first candidate | 5/5 | 5/5 | 3/5 |

## Architecture

```mermaid
flowchart TD
    U[Human goal and constraints<br/>"Hold level at 0.6, never overflow,<br/>minimize pump energy"] --> UI[Praxion dashboard + REST/SSE]
    UI --> O[Praxion orchestrator<br/>finite-state loop, budgets, event log]
    O --> M[Meta Muse via Meta Model API<br/>muse-wonder-1.0 / muse-spark-1.3<br/>hypothesize / propose experiment / author code / revise]
    M -->|Structured experiment proposal| V[Safety supervisor + action validator<br/>limits, budgets, worst-case bound, interlock, e-stop]
    V -->|Approved bounded commands| A[PlantAdapter<br/>observe / apply_input / reset / emergency_stop]
    A --> S1[TankSimulator<br/>hidden dynamics + noise + disturbance]
    A --> S2[Second plant<br/>not built]
    S1 --> T[Telemetry store<br/>time series, experiment id, source]
    S2 --> T
    T --> O
    M -->|controller_vN.py source| C[Controller registry<br/>sha256, parent, diff, prompt hash, model id]
    C --> G[Static checks + Docker sandbox<br/>no net, read-only fs, non-root, limits]
    G -->|Passes interface tests| E[Independent evaluator<br/>hidden seeds, disturbance suites, baselines, ablation]
    E -->|Pass/fail + metrics| O
    E -->|Approved version only| R[Trusted local controller runtime<br/>fixed rate, no cloud in fast loop]
    R --> V
    T --> D[Evidence: charts, timeline, ledger, diffs, scores]
    E --> D
    C --> D
    D --> UI
    O -->|Budget exhausted or gates met| F[Artifact bundle<br/>result.json, event_log.jsonl, model_calls.jsonl,<br/>controller sources, diffs, machine cards, evaluations]
    style M fill:#243b55,color:#fff,stroke:#79b2ff
    style V fill:#593e20,color:#fff,stroke:#efbc68
    style G fill:#593e20,color:#fff,stroke:#efbc68
    style E fill:#214d3d,color:#fff,stroke:#65c99f
```

**Three trust zones.**
- *Untrusted:* everything Muse returns, including controller source.
- *Semi-trusted:* a candidate controller executing inside the sandbox.
- *Trusted:* orchestrator, supervisor, simulator, evaluator, registry, monitor.

**Two time scales.** Muse runs between experiments and rollout segments, one structured call at a time. The approved controller runs locally at a fixed simulated rate under the supervisor. The deployed loop and the safety limits never wait on the cloud.

**One egress.** The model sees only what `backend/agent/view.py` builds: the public plant description, objective, constraints, noisy measured traces, facts about its own commands, trusted summaries computed only from measured level and applied input, its own ledger, and agent-safe evaluation summaries. It never sees plant parameters, hidden scenario seeds, the disturbance family or mechanism, the simulator source, the true level, or the baselines. `tests/test_agent_blindness.py` enforces this.

**Docker sandbox.** Model-authored code runs only in `python:3.12-slim` with `--network none --read-only --user 65534:65534 --cap-drop ALL --security-opt no-new-privileges --memory 256m --memory-swap 256m --pids-limit 64 --cpus 1` and a small noexec `/tmp` tmpfs (`backend/controller/sandbox.py`). The status doc records 18 hostile candidates (network, file, fork, dunder escapes, exec, memory bomb, CPU burn, infinite loop, huge state), all contained with the static checker bypassed. A subprocess fallback exists for development only and is labeled in the UI.

**Independent evaluator and hidden scenarios.** Scores come from `backend/evaluation/`, on held-out scenario seeds 1000 to 1009 and disturbance seeds 2000 to 2004. Seeds, windows and thresholds are frozen in `backend/evaluation/config.py` before scoring. Within a run, the evaluator tests this machine on unseen scenarios (different initial level, noise stream, disturbance magnitude). Cross-machine evidence comes from repeating the whole protocol over plant seeds 3, 7, 11, 14 and 18.

**Trusted monitor and interlock.** The monitor calibrates on a window ending at 58 s. It fires when the 15 s window MAE stays above max(2 × baseline, 0.05) for 10 s, or when any supervisor override occurs after calibration. An independent high-level interlock on the true simulated level (at 0.90) forces `u = 0` and an emergency stop, which also flushes the actuator delay line. Overrides and violations count against the candidate, never in its favor.

## Why the disturbance is a transport delay

Feedback absorbs offset disturbances. A plain PI controller rejects a weaker pump, an extra leak or a drain shift by construction. Across all five machines, the fixed PID's post-change MAE on the three offset families stays between 0.0026 and 0.0055 (`docs/BENCHMARKS.md`, every run section). An offset change therefore cannot test whether an agent adapts. Only a change in dynamics can. We added the `actuator_lag` family: time constant ×1.0 to 1.5 plus an 18 to 22 s transport delay. Slowing the actuator alone does not break PI. Pure delay does. Under the delay, the fixed PID's post-change in-band fraction falls to 0.312 to 0.416. A slow PID tuned by hand stays in band 0.979 to 1.000 with zero violations, so the change is repairable. That slow PID was tuned post hoc on the disturbance seeds. It is an existence proof, not a fair rival. (`docs/BENCHMARKS.md`, every run section)

The offset families stay in the benchmark to show the monitor correctly staying quiet when feedback already handles the change. The detector sweep in the status doc: floor 0.05 caught 24/25 lag cases with 0 false alarms across 150 offset and nominal cases.

## Gates and current status

Gate definitions are in `PRAXION_IMPLEMENTATION_PLAN.md` section 10 and frozen in `backend/evaluation/config.py`.

- **G0 foundation:** tests green (status doc: 415 passed), baselines hold band, sandbox contains the hostile corpus (18/18), real API reply recorded.
- **G1 discovery:** ≥ 3 distinct experiments tied to the ledger, ≥ 1 valid verbatim Muse controller.
- **G2 performance:** ≥ 8/10 held-out scenarios, zero violations and overrides, ≥ 0.70 in-band after settling.
- **G3 self-repair:** the repair cuts post-change MAE by ≥ 20% vs frozen v1 on ≥ 3/5 disturbance scenarios, with zero hard violations and zero invalid outputs.

**Cross-run summary per protocol**, copied verbatim from `docs/BENCHMARKS.md` (generated 2026-10-31T04:19:54-0400 by `uv run python scripts/run_evaluation.py --sandbox docker`, evaluator fingerprint `e5baf63fb34cf61a`). Every candidate source is re-hashed and scored fresh on the frozen scenarios. G3 applies the current promotion rule. A run that never reached repair counts as not passed.

| prompt version | runs | G1 | G2 | G3 | G3 not reached | median experiments to v1 | median cost USD | median wall s |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| v1.0 | 2 | 2/2 | 2/2 | 0/2 | 1 | 10.0 | 0.600 | 763.2 |
| v1.1 | 1 | 1/1 | 1/1 | 1/1 | 0 | 11.0 | 2.053 | 923.4 |
| v1.2 | 5 | 5/5 | 4/5 | 4/5 | 0 | 10.5 | 1.653 | 775.5 |
| v1.3 | 5 | 5/5 | 5/5 | 5/5 | 0 | 12.0 | 1.719 | 816.8 |

Notes. v1.1 shows G3 1/1 because fresh scoring applies the current rule. That run (`spark3-20261031-010142-feac7f`) recorded FAILED under the rule then in force, and the recorded verdict stands. The v1.2 G3 4/5 counts `spark6-20261031-012958-e01d87`, which failed G2 and never deployed. The Wonder run (`wonder1-20261031-010124-6130b3`) is skipped by the benchmark because it stopped before any evaluation.

**Protocol v1.3, per machine** (source `docs/IMPLEMENTATION_STATUS.md`; prompt hash `0d19650e641cac11`; every bundle passes `scripts/audit_run.py` 7/7):

| Plant seed | Run | Discovery exps | v1 G2 (in-band) | Frozen v1 post-change MAE / hard viol. | Promoted repair | Post-change MAE / in-band / hard viol. | Median reduction | Nominal kept (in-band) | Diagnosis | Cost | Time |
|---:|---|---:|---|---|---|---|---:|---|---|---:|---:|
| 3 | `v13-s3-20261031-015222-39a872` | 12 | PASS (0.89) | 0.186 / 21 | v3 (attempt 2) | 0.031 / 0.87 / 0 | −84% | no (0.36) | correct | $2.17 | 17 min |
| 7 | `v13-s7-20261031-020602-18f408` | 12 | PASS (0.78) | 0.190 / 7 | v2 | 0.095 / 0.32 / 0 | −50% | no (0.56) | correct | $1.71 | 11 min |
| 11 | `v13-s11-20261031-020922-a0e68e` | 12 | PASS (0.92) | 0.217 / 2 | v2 | 0.021 / 1.00 / 0 | −91% | yes (0.93) | correct | $1.75 | 11 min |
| 14 | `v13-s14-20261031-015222-af63b9` | 11 | PASS (1.00) | 0.044 / 0 | v2 | 0.010 / 1.00 / 0 | −78% | yes (1.00) | correct | $1.72 | 14 min |
| 18 | `v13-s18-20261031-021658-2cc943` | 12 | PASS (1.00) | 0.027 / 0 | v2 | 0.014 / 0.94 / 0 | −59% | yes (1.00) | correct | $1.71 | 17 min |

Summary: G1 5/5, G2 5/5 on the first candidate, G3 5/5, diagnosis 5/5, nominal kept 3/5.

### The promotion rule

A repair is promoted on the changed machine's criteria only: ≥ 3/5 disturbance scenarios with ≥ 20% lower post-change MAE than frozen v1, zero hard violations, and zero invalid outputs. Nominal G2 after repair is re-scored and reported, as in the "nominal kept" column, but it does not gate promotion. The repaired controller is for the machine as it now is. Requiring it to also pass on the machine that no longer exists is a robustness demand, not self-repair. We decided this on 2026-10-31, while no run had yet passed Gate 3 (decisions log in `docs/IMPLEMENTATION_STATUS.md`). Run spark3 recorded FAILED under the earlier rule, which also required nominal G2. That recorded verdict was not rewritten.

## Quickstart

Requirements: Python 3.12 with `uv`, Docker (for the sandbox), Node.js (for the dashboard).

```bash
uv sync
```

Put your Meta Model API key in `~/meta.key`, or set `MODEL_API_KEY`. The key is never printed or logged.

```bash
uv run pytest -q                       # mock agent, no credits
uv run pytest -q -m docker             # sandbox tests, needs a Docker daemon
uv run python scripts/check_meta.py    # connectivity check against the Meta Model API
```

Run the full loop live. This spends credits and records a bundle under `artifacts/runs/`:

```bash
uv run python scripts/run_live_demo.py --model muse-spark-1.3 --plant-seed 7 --disturbance actuator_lag
```

Dashboard:

```bash
cd frontend && npm install && npm run build && cd ..
uv run uvicorn backend.main:app --port 8000
# open http://127.0.0.1:8000
```

Replay a recorded run. Replay re-emits the stored event log at recorded pacing and is labeled REPLAY with the run id and recording time. Nothing is recomputed.

```bash
uv run python scripts/replay_run.py v13-s11-20261031-020922-a0e68e --speed 16
```

Audit a bundle and regenerate the benchmark tables:

```bash
uv run python scripts/audit_run.py <run_id>
uv run python scripts/run_evaluation.py   # rewrites docs/BENCHMARKS.md from stored bundles
```

## Repository map

| Path | Contents |
|---|---|
| `backend/agent/` | Muse client, prompts, agent view (the single egress), orchestrator stage machine, mock agent for CI |
| `backend/plant/` | `TankSimulator` and the `PlantAdapter` interface |
| `backend/safety/` | supervisor, interlock, exploration envelope |
| `backend/controller/` | static checker, Docker sandbox, interface tests, registry, runtime |
| `backend/evaluation/` | frozen config, metrics, baselines, suites, monitor, benchmarks |
| `backend/api/`, `backend/main.py` | FastAPI REST + SSE over the artifact bundles |
| `frontend/` | Vite + React dashboard: plant, agent timeline and ledger, code and diff, evidence |
| `scripts/` | live run, replay, demo recording, audit, evaluation, export, connectivity check |
| `tests/` | unit, blindness, sandbox (`-m docker`), live (`-m live`) tests |
| `artifacts/runs/<run_id>/` | recorded bundles |
| `docs/` | status, benchmarks, safety limitations, demo script, provenance |

## Evidence and honesty

**What `scripts/audit_run.py` checks** on a bundle, with nothing but the bundle:
1. Every `controller_vN.py` sha256 and length match its `meta.json`, and `result.json` lists the same candidates.
2. Every agent view snapshot passes the leak scanner `find_leaks`.
3. `model_calls.jsonl` exists, successful calls use `muse-*` model ids (mock ids are flagged), and token and cost totals match `result.json`.
4. Event log sequence numbers are strictly increasing and contiguous, and every stage transition is allowed by the stage machine.
5. Each `candidate_registered` event's hash and length match the stored file.
6. Each registered source is byte-identical to the `source_code` in the authoring model call's response. This is the authorship proof.
7. No disturbance family name appears in any model request message.

**What the blindness test checks.** `tests/test_agent_blindness.py` builds views from rich synthetic sessions and from every stored snapshot of every recorded run. The leak scanner has three layers. Layer 1 rejects trusted keys anywhere in the view (for example `h_true`, `hidden_params`, `plant_seed`, `disturbance_family`, plant parameter names). Layer 2 rejects specific trusted identifiers in any value, model text included: parameter names, every disturbance family name, baseline names. Layer 3 rejects whole numbers in the hidden seed ranges 1000 to 1019 and 2000 to 2019 everywhere except model-authored free text. The scanner was redesigned after it stopped a Wonder run on a false positive (the word "hidden" in Muse's own ledger), and all recorded runs were re-audited.

**Mock and replay labeling.** Mock mode exists for CI only. Mock runs are excluded from benchmarks unless asked for, and the dashboard shows "MOCK · not model output". Replay shows a REPLAY badge with speed, run id and recording time. Runs that used the dev-only subprocess sandbox carry a warning badge.

**Frozen config policy.** Metrics, windows, seeds and thresholds live in `backend/evaluation/config.py`. Every change to them is logged in the status doc with a reason, and each was made before official scoring. When Muse underperforms, we change the protocol, never the controller, the scores or the seeds. Each protocol version has a logged prompt hash. Protocol v1.3 is frozen for the submission.

**What the operator API exposes.** The dashboard API serves trusted data to the human operator, including the disturbance family and the hidden plant parameters in the evaluation audit entries. The operator is not the agent. None of it passes through `agent/view.py`, and audit checks 2 and 7 verify that on every bundle.

## Safety limitations

Full list: [`docs/SAFETY_LIMITATIONS.md`](docs/SAFETY_LIMITATIONS.md).

- The interlock is an ideal model: it reads the true simulated level with no noise, delay or failure modes. The true level can still exceed 0.90 by up to about 0.01.
- The exploration envelope ignores commands already queued in the actuator delay line and starts from the noisy measurement.
- The supervisor's measurement-based cutoff reacts late under delay. It cannot undo inflow that is already committed.
- A repair is specific to the change it was written for. Promoted repairs detune for the measured delay and then absorb offset changes (weaker pump, extra leak) worse than the original controller did: `v13-s11` v2 under `pump_derate` has post-change MAE 0.1856 and in-band 0.33, against 0.0098 for its v1 (`docs/BENCHMARKS.md`). A machine that reverts or changes a second way needs another monitored repair cycle.
- Simulation establishes nothing about real hardware. No claim here transfers to a physical tank, pump or sensor without separate validation.

## Model usage and cost

Each protocol v1.3 run cost $1.71 to $2.17 and took 11 to 17 min (`docs/IMPLEMENTATION_STATUS.md`; `result.json` `elapsed_s` 651.1 to 1047.3 s). Input tokens dominate the cost, because candidate evaluation traces go into the view. Run `v13-s11` used 992,743 prompt tokens for 18 calls.

Estimated spend for every live run, from each `result.json` `model_usage.cost_usd`:

| Run | Model | Protocol | Calls | Cost USD |
|---|---|---|---:|---:|
| `spark-20261031-002956-c19d0d` | muse-spark-1.3 | v1.0 | 14 | 0.498 |
| `spark2-20261031-004636-3d012e` | muse-spark-1.3 | v1.0 | 12 | 0.702 |
| `spark3-20261031-010142-feac7f` | muse-spark-1.3 | v1.1 | 19 | 2.053 |
| `wonder1-20261031-010124-6130b3` | muse-wonder-1.0 | v1.1 | 9 | 2.243 |
| `spark4-20261031-011710-0c4353` | muse-spark-1.3 | v1.2 | 18 | 1.653 |
| `spark5-20261031-011712-e34d36` | muse-spark-1.3 | v1.2 | 16 | 1.360 |
| `spark6-20261031-012958-e01d87` | muse-spark-1.3 | v1.2 | 18 | 1.960 |
| `spark7-20261031-012959-a9c6d6` | muse-spark-1.3 | v1.2 | 21 | 4.300 |
| `spark8-20261031-013049-bc09a1` | muse-spark-1.3 | v1.2 | 13 | 1.445 |
| `v13-s3-20261031-015222-39a872` | muse-spark-1.3 | v1.3 | 19 | 2.168 |
| `v13-s7-20261031-020602-18f408` | muse-spark-1.3 | v1.3 | 18 | 1.715 |
| `v13-s11-20261031-020922-a0e68e` | muse-spark-1.3 | v1.3 | 18 | 1.747 |
| `v13-s14-20261031-015222-af63b9` | muse-spark-1.3 | v1.3 | 18 | 1.719 |
| `v13-s18-20261031-021658-2cc943` | muse-spark-1.3 | v1.3 | 18 | 1.711 |
| **Total, 14 live runs** | | | | **25.274** |

The 13 Spark runs total $23.031. The Wonder run adds $2.243. Spark is the primary model: it is 3 to 4 times cheaper, and its operator notes were coherent, while Wonder's single run had hallucinated notes (`docs/IMPLEMENTATION_STATUS.md`).

## License and provenance

MIT License, Copyright (c) 2026 Mithran Selvaraj.

How the code was written, what Muse authored, the protocol history, every run id, and which third-party libraries are used: [`docs/PROVENANCE.md`](docs/PROVENANCE.md).
