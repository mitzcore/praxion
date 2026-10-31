# CLAUDE.md — Praxion

## Objective

**Win the Indie developer track of the Meta Global AI Developer Hackathon (Oct 26 – Nov 4, 2026) with Praxion: an agent that discovers how an unfamiliar physical machine behaves, writes its own controller, tests it against hidden scenarios, and repairs its own code when the machine changes. The reasoning, experiment design, controller code, and repairs are authored by Meta Muse models (`muse-wonder-1.0`, fallback `muse-spark-1.3`) through the Meta Model API. Everything shown to judges must have actually happened and be reproducible from the artifact bundle.**

Judging criteria for the track (verbatim from the event page): *creativity, technical ambition, and whether it works.*

- **Deadline:** Nov 4, 2026, 9:00 PM ET. Internal target: submitted by 6:00 PM ET.
- **Theme:** Push the Frontier (robotics / manufacturing / energy).
- **Scope decision (Oct 31):** Phase-1 MVP only, pure simulation, one plant (water tank). No Raspberry Pi. A second plant is a stretch only after the depth bar is met.
- **Owner and presenter:** Mithran. **Lead engineer and driver:** Claude.

Full design: `PRAXION_IMPLEMENTATION_PLAN.md`. Living status: `docs/IMPLEMENTATION_STATUS.md`. The archived Codex plan in `docs/archive/` is superseded.

## Depth over breadth (the operating philosophy)

Mithran's instruction: *a deeper product, not a bigger one.* Depth means the core loop is extraordinary and every claim survives a hostile expert's scrutiny. Concretely:

1. **One loop, done to the bone.** Discover → author → validate → score → break → diagnose → repair → re-score. No feature is added until the loop's weakest link is fixed.
2. **Question the outcome at every phase exit.** Before moving on, answer in writing (status doc): What did this phase prove? What would a skeptical control engineer or ML researcher say is fake, lucky, or leaked? What is the single weakest link? Fix that first.
3. **Measure distributions, not anecdotes.** Run the live pipeline N ≥ 5 times on frozen seeds. Report success rate, medians, and failures. One good run is a demo; a distribution is evidence.
4. **Iterate on the protocol, never the output.** When Muse underperforms, improve the experiment protocol, the agent view, the prompts, or the failure traces. Never touch the controller, the scores, or the seeds.
5. **Falsifiability built in.** Blindness test, hostile-code sandbox corpus, same-seed comparisons, frozen-v1 ablation, transparent PID baseline. If PID wins, that is the result.
6. **Every artifact is self-evidencing.** Hash, model id, prompt hash, timestamps, redacted prompts and completions. A judge can reconstruct the run from the bundle alone.

## The one thing to get right

Muse proposes a bounded experiment → simulator responds → Muse revises its hypothesis ledger → Muse authors `controller_v1.py` → static check + Docker sandbox → independent evaluator scores on hidden seeds → deploy under trusted runtime → hidden disturbance → trusted monitor detects degradation → Muse diagnoses from traces and authors `controller_v2.py` → same-seed re-test → promote only if better and safe.

## Non-negotiable rules

1. **Muse authors the controller.** Source stored byte-for-byte, hashed, diffed, with model id and prompt hash. Trusted code never patches, retunes, or rewrites it. Baseline PID/on-off exist only for scoring and are never shown to the model.
2. **The agent is blind.** The runtime model sees only `backend/agent/view.py` output: public plant description, objective, constraints, noisy `y` traces, its own ledger, agent-safe evaluation reports. Never parameters, hidden seeds (1000s, 2000s), disturbance mechanisms, simulator source, or `h_true`. `tests/test_agent_blindness.py` enforces this.
3. **Isolation.** Model-authored Python runs only inside the Docker sandbox (no network, read-only, non-root, limits). The subprocess fallback is dev-only and labeled in the UI.
4. **Trusted code has final authority.** The supervisor owns `u_applied`. Hard cutoff, stale sensor, e-stop → `u=0`. Overrides are logged and scored against the candidate.
5. **No fabricated evidence.** No invented API responses, scores, improvements. Mock mode is CI-only and labeled. Replay is labeled with run id and timestamp. Failed gates are reported.
6. **Same-seed comparisons.** v1 vs v2 vs baselines on identical frozen seeds; metrics and windows frozen in `backend/evaluation/config.py` before scoring.
7. **Honest claims.** No "any machine", no "guaranteed safe", no "beats PID" without data.

## Who does what (model roles)

- **Fable 5.1 (this session):** reasoning, architecture, trust-boundary code (`agent/view.py`, `agent/orchestrator.py`, `agent/prompts.py`, `evaluation/config.py`), briefs, code review, running tests, depth reviews, decisions, status doc.
- **Opus 5.5 subagents (`model: "opus"`):** all implementation work from precise briefs: module, interface it must satisfy, tests it must add, files it owns, what it must not touch. One module family per agent; independent modules run in parallel. Each brief ends with "run `uv run pytest -q` and report exact output."
- Fable verifies every subagent result by running the tests itself and reading the diff before accepting it.

## Phase plan (exit criteria, not dates; details in plan section 12)

| Phase | Builds | Exit criterion |
|---|---|---|
| **0 Ground truth** | scaffold, seeded tank sim, PlantAdapter, supervisor + envelope, metrics + frozen config, PID/on-off baselines, static checker, Docker sandbox, hostile corpus | tests green; baselines hold band; sandbox blocks hostile corpus; real API reply recorded |
| **1 Discovery → v1** | MuseClient (structured, retries, cost), prompts v1, agent view + blindness test, orchestrator through EVALUATING, registry, evaluator suites + gates, artifact bundle | one live run yields a scored, hashed `controller_v1.py` bundle |
| **2 Break → repair** | monitor, disturbance families, ADAPTING stage, same-seed v1/v2 compare, ablation runner, `BENCHMARKS.md` | Gate 3 measured and recorded, pass or fail |
| **3 Evidence surface** | FastAPI + SSE, dashboard (plant, timeline+ledger, diff, evidence), replay, export | UI shows only stored events; a recorded run replays faithfully |
| **4 Depth iteration** | N ≥ 5 live runs per protocol version; failure-mode analysis; protocol/prompt/view improvements; re-run | best measured distribution; every weakest link addressed or documented |
| **5 Ship** | README, SAFETY_LIMITATIONS, DEMO_SCRIPT, 3-min video from a real run, public repo, secrets scan | submitted ≥ 3 h before deadline |

Each phase ends with a **depth review** written into `docs/IMPLEMENTATION_STATUS.md` (proved / weakest link / what a skeptic says / decision).

## Stack and commands

Python 3.12 via `uv`; FastAPI, Pydantic v2, numpy, scipy, openai SDK, pytest, ruff. Frontend: Vite + React + Recharts + diff viewer. Sandbox: Docker `python:3.12-slim` with `--network none --read-only --user 65534 --cap-drop ALL --memory 256m --pids-limit 64 --cpus 1`. Storage: SQLite + JSONL under `artifacts/runs/<run_id>/`.

```bash
uv sync
uv run pytest -q                          # must stay green; mock agent, no credits
uv run pytest -q -m live                  # real Muse calls
uv run pytest -q -m docker                # sandbox tests
uv run python scripts/check_meta.py       # connectivity; reads ~/meta.key if MODEL_API_KEY unset
uv run uvicorn backend.main:app --reload
cd frontend && npm run dev
uv run python scripts/run_live_demo.py --disturbance pump_derate
uv run python scripts/run_evaluation.py   # regenerates docs/BENCHMARKS.md
uv run python scripts/replay_run.py <run_id>
```

Key loading order: `MODEL_API_KEY` env → `MODEL_API_KEY_FILE` → `~/meta.key`. Never print or log the key.

## Meta Model API facts (verified by live calls Oct 31, 2026)

- Base `https://api.meta.ai/v1`, OpenAI SDK, key passed explicitly.
- `muse-wonder-1.0` ($4/$20 per 1M in/out) and `muse-spark-1.3` ($1.25/$4.25). Both answered; ~1–11 s latency; `usage.completion_tokens_details.reasoning_tokens` is populated. `reasoning_effort` is accepted on Chat Completions.
- Structured output verified: `response_format={"type":"json_schema","json_schema":{"name":..., "schema":..., "strict": true}}` with nested `$defs` and `additionalProperties: false` on every object; both models returned schema-valid JSON.
- Observed: Spark set `ready_to_generate=true` with zero experiments. Prompts and trusted code must gate readiness on a minimum of evidence (≥ 3 completed experiments, ledger confidences justified).
- Tool calling: only `tool_choice="auto"`. We use stage-driven structured calls (plan 6.2).
- Retry 429 with backoff + jitter; honor `Retry-After`. Log model id, tokens, est. USD per call to `model_calls.jsonl`, redacted. Never use `*-contributor` variants.

## How Claude works in this repo

- Start of session: read `docs/IMPLEMENTATION_STATUS.md`, pick the highest-priority unverified item in the current phase.
- "Done" means tests pass and the status doc names the proving command. "Live-verified" means artifacts exist under `artifacts/`.
- Small conventional commits after each verified milestone (`feat(sim): ...`), only when Mithran asks or has authorized it for the session. Never commit `.env`, keys, `artifacts/runs/`.
- Prompt changes bump `PROMPT_VERSION` in `backend/agent/prompts.py` and are logged in the status doc with the reason and the measured effect.
- Stuck > 30 min on a non-critical item → record blocker, move on.
- Do not build: Pi adapter, SAM, voice, image, fine-tuning, RL, Kubernetes, queues, microservices.

## Gates (details in plan section 10)

G0 foundation · G1 discovery (≥ 3 distinct experiments tied to ledger, ≥ 1 valid verbatim Muse controller) · G2 performance (≥ 8/10 held-out, zero violations/overrides, ≥ 70% in-band after settling) · G3 self-repair (v2 cuts post-disturbance MAE ≥ 20% vs frozen v1 on ≥ 3/5 seeds, zero violations) · G3b transfer (stretch).
