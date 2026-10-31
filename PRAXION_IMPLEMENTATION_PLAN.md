# Praxion — Autonomous Physical Controller Discovery

**Claude implementation specification | Meta Global AI Developer Hackathon (Oct 26 – Nov 4, 2026)**
**Track:** Indie developer track (judged on *creativity, technical ambition, and whether it works*)
**Theme:** Push the Frontier ("software, robotics, manufacturing, energy, materials and beyond")
**Submission deadline:** November 4, 2026, 9:00 PM Eastern Time. Judging Nov 4–8, winners Nov 9.
**Status:** Engineering design. Nothing is built yet. No performance claims exist yet.
**Runtime:** Python 3.12 (via `uv`), FastAPI, Meta Model API (`muse-wonder-1.0` / `muse-spark-1.3`), React + Vite
**Scope (decided Oct 31):** Phase-1 MVP only: pure simulation, one unknown water tank, the full discover → author → validate → break → repair loop, done to the bone. Raspberry Pi is out. A second simulated plant is a stretch after the depth bar is met.
**Operating model:** Fable 5.1 reasons, architects, owns the trust boundary, validates and orchestrates. Opus 5.5 subagents implement from precise briefs. Every phase ends with a written depth review.

This document supersedes `docs/archive/WORLDPATCH_CODEX_IMPLEMENTATION_PLAN.md`. Facts about the hackathon and the Meta API below were verified against the live pages on Oct 30, 2026 and corrected where the archived plan was wrong.

---

## 0. How Claude uses this document

You (Claude Code) are the lead engineer and the driver of this project. The human is the product owner and the demo presenter. The operating rules live in `CLAUDE.md`; this file is the full design. Read both before touching code.

Work in priority order (section 12). Deliver the **smallest complete loop** first, then widen. Keep `docs/IMPLEMENTATION_STATUS.md` current: what works, what is verified by a test or a real run, what is blocked, and the exact command to reproduce each claim.

**Never:**

- Invent API responses, benchmark numbers, controller improvements, or hardware results.
- Hand-write the controller the demo presents as Muse-authored.
- Give the runtime agent plant parameters, hidden seeds, simulator source, or evaluation internals.
- Execute model-authored Python on the host without isolation.
- Let a chart, log, or timeline show anything that did not actually happen in the stored run.

**Definition of a successful project:** A previously unseen simulated physical plant is exposed through a restricted tool interface. Muse chooses informative, safe experiments; reads the measurements; writes a hypothesis ledger and a controller; the controller is validated in isolation and scored on hidden held-out scenarios; the plant is then changed without telling Muse how; Muse diagnoses the degradation from measurements alone and authors a materially different controller version that measurably recovers. Every step is auditable from one artifact bundle.

**Definition of failure:** Muse only narrates; a developer secretly supplies the working controller; Muse sees hidden parameters; improvements are asserted without same-seed measurements; an unvalidated artifact is deployed to hardware.

---

## 1. Why this can win the indie track

The indie track criteria are **creativity, technical ambition, whether it works**. Map every build decision to those three.

| Criterion | What Praxion shows the judge | Where it must be visible |
|---|---|---|
| Creativity | An agent that *does science on a machine*: forms hypotheses, runs experiments, writes code, breaks, repairs. Not a chatbot over telemetry. | Hypothesis ledger, "machine card", v1→v2 diff |
| Technical ambition | Closed loop between a frontier model and a physical-dynamics system with real safety architecture: sandboxed model code, independent evaluator, hidden seeds, two time scales. Second plant family proves the protocol is not tank-specific. | Architecture diagram, ablation table, transfer run |
| Whether it works | Live or faithfully replayed run with real `muse-*` calls, real measured scores, failures shown. One command reproduces the evaluation. | `scripts/run_evaluation.py`, `docs/BENCHMARKS.md`, 3-minute video |

**The single judge moment that wins:** v1 is frozen, the operator presses "Introduce Disturbance", tracking error climbs, Muse reads the failure trace and emits `controller_v2.py` whose diff shows a *reasoned* change (e.g., adds integral action, re-estimates gain online, adds feed-forward), and the same-seed re-test shows recovery. Everything else exists to make that moment true and auditable.

**Differentiators to protect** (cut anything that threatens them):

1. Muse authors the code. Verbatim, hashed, diffed.
2. The agent is blind to the truth. Enforced by the tool boundary and testable.
3. Scores come from an evaluator the agent cannot touch, on seeds it never sees.
4. Honesty is a feature: failures, overrides, and baseline comparisons are displayed, not hidden.

---

## 2. Vision, hypothesis, and claims

### One-sentence pitch

> **Praxion gives an unfamiliar machine a small adaptive engineer: Meta Muse designs safe experiments, learns how the machine responds, writes a controller, tests it against hidden scenarios, and repairs its own code when the machine changes.**

### Central technical hypothesis

A general-purpose frontier model, connected to an intentionally restricted physical-system interface, can autonomously discover enough about an unfamiliar dynamical system to author a useful control policy and adapt it after a disturbance, **without being given a machine-specific controller or the system's parameters.**

### What this is not

Not a proof that any machine can be safely automated. Not a new invention of PID or system identification. Not zero-shot industrial automation. Not certified safety. Not production readiness. It demonstrates an *agentic control-engineering workflow* on black-box simulations.

### Muse's contribution must be essential and observable

Muse performs all four reasoning tasks, and the UI shows each:

1. **Hypothesize:** State what could explain the observed response and what is uncertain, with confidence.
2. **Experiment:** Choose bounded inputs and durations that discriminate between hypotheses.
3. **Synthesize:** Author a complete, executable `control(obs, state)` function from the evidence.
4. **Revise:** Use measured failure to author a *meaningfully changed* controller and explain the change.

Trusted Python may simulate physics, enforce limits, run tests, compute metrics, and detect degradation. It may **not** author or retune the controller and present that as Muse's work.

---

## 3. Scope: depth over breadth

**In scope (the product):** one unknown simulated water tank; the complete loop discover → author → validate → score → deploy → break → diagnose → repair → re-score; an evidence surface that shows only stored events; a benchmark distribution over repeated live runs; an honest ablation.

**Out of scope:** Raspberry Pi and all hardware; SAM, voice, image; fine-tuning; RL; a second plant until the depth bar below is met.

**The depth bar** (what "done to the bone" means for this loop; each item is a measurable property, not a feature):

| Dimension | Shallow version | Deep version Praxion must reach |
|---|---|---|
| Experiment design | Muse picks arbitrary steps | Each experiment names the ledger uncertainty it reduces and predicts the observation; experiment efficiency (experiments to a passing v1) is measured and reported |
| Hypothesis ledger | Free text | Structured hypotheses with confidences revised after every experiment; the ledger history is an artifact |
| Controller authorship | "Looks like Muse wrote it" | Byte-identical registry, hash, prompt hash, model id; a test asserts registry bytes equal the model's output; baselines never in prompts |
| Blindness | "We didn't tell it" | `agent_view()` is the single egress; a test scans every snapshot for parameter names, values, hidden seeds, disturbance names |
| Isolation | AST lint | Docker sandbox proven against a hostile-candidate corpus (network, file, fork, memory bomb, infinite loop, dunder escape) |
| Evaluation | One good run | Frozen config; hidden seeds; same-seed v1/v2/baselines; N ≥ 5 live runs per protocol version; medians and failures reported |
| Repair | v2 "is different" | Trusted degradation detector with logged thresholds; Muse's diagnosis is recorded and judged against the actual hidden mechanism *after the fact* (diagnosis accuracy is a reported metric) |
| Honesty | Claims in README | Ablation table, PID baseline row, override accounting, replay labeling, provenance |

**Diagnosis accuracy** is the one new metric this depth pass adds: the evaluator records the hidden disturbance family; after the run, trusted code compares it against Muse's `diagnosis` text category (Muse must pick from `{"actuator_weaker","outflow_increased","sensor_changed","unknown"}` in addition to free text). This turns "Muse explained the failure" into a scored claim.

**Stretch (only after Phases 0–4 pass depth review):** a thermal-chamber plant with unchanged orchestrator and prompts (plan 5.2). It stays in the architecture as an interface, not as scheduled work.

---

## 4. Architecture

One integrated diagram: components, feedback loops, generated code path, isolation, adapters, evaluation, outputs.

```mermaid
flowchart TD
    U[Human goal and constraints<br/>"Hold level at 60%, never overflow,<br/>minimize pump energy"] --> UI[Web dashboard + REST/SSE]
    UI --> O[Orchestrator<br/>finite-state loop, budgets, event log]
    O --> M[Meta Muse<br/>muse-wonder-1.0 primary, muse-spark-1.3 fallback<br/>hypothesize / propose experiment / author code / revise]
    M -->|Structured experiment proposal| V[Safety supervisor + action validator<br/>limits, budgets, worst-case bound, e-stop]
    V -->|Approved bounded commands| A[PlantAdapter<br/>observe / apply_input / reset / emergency_stop]
    A --> S1[TankSimulator<br/>hidden dynamics + noise + disturbance]
    A --> S2[Second plant - stretch only<br/>same interface]
    S1 --> T[Telemetry store<br/>time series, experiment id, source]
    S2 --> T
    T --> O
    M -->|controller_vN.py source| C[Controller registry<br/>sha256, parent, diff, prompt hash, model id]
    C --> G[Static checks + isolated execution<br/>Docker: no net, ro fs, non-root, limits]
    G -->|Passes interface tests| E[Independent evaluator<br/>hidden seeds, disturbance suites, baselines, ablation]
    E -->|Pass/fail + metrics| O
    E -->|Approved version only| R[Trusted local controller runtime<br/>fixed-rate, no cloud in fast loop]
    R --> V
    T --> D[Evidence: charts, timeline, ledger, diffs, scores]
    E --> D
    C --> D
    D --> UI
    O -->|Budget exhausted or gates met| F[Artifact bundle<br/>result.json, sources, diff, plots, report.md]
    style M fill:#243b55,color:#fff,stroke:#79b2ff
    style V fill:#593e20,color:#fff,stroke:#efbc68
    style G fill:#593e20,color:#fff,stroke:#efbc68
    style E fill:#214d3d,color:#fff,stroke:#65c99f
```

**Two time scales.** Muse runs *between* experiments and rollout segments (seconds to a minute per call). The approved controller runs locally at a fixed interval (0.2–1.0 s simulated) under the safety supervisor. Cloud availability is never required to hold a deployed policy or enforce limits.

**Trust boundaries.** Three zones. *Untrusted:* Muse output and generated controller source. *Semi-trusted:* the sandboxed execution of a candidate. *Trusted:* orchestrator, supervisor, simulator, evaluator, registry. Data flows from trusted to untrusted only through the agent-visible projection (section 6.3).

---

## 5. The unfamiliar plants

### 5.1 Plant A (P0): water-level control

A reservoir with a controllable inlet pump, an uncontrolled outflow, a noisy level sensor, and a target level. Chosen because it is visual, intuitive to judges, nonlinear enough to be interesting (sqrt drain), and transferable to real hardware.

**Agent sees:** target, allowed input range, measured level over time, elapsed time, its own past experiments and their traces, limits, candidate evaluation reports (metrics and agent-safe traces only).
**Agent never sees:** tank area, pump gain, deadband, actuator lag, drain coefficient, leak, noise std, disturbance schedule or mechanism, evaluation seeds, simulator source.

**Internal dynamics (trusted code only; never in prompts):**

```text
u_cmd(t) in [0, 1]
u_act(t+dt) = clamp(u_act(t) + (dt/tau) * (u_cmd(t) - u_act(t)), 0, 1)       # actuator lag
q_in  = pump_gain * eff(t) * max(0, u_act - deadband) / max(1e-6, 1 - deadband)
q_out = leak_base + leak_extra(t) + drain_coeff * sqrt(max(h, 0))
h(t+dt) = clamp(h(t) + dt * (q_in - q_out) / tank_area, 0, 1)
y(t)  = clamp(h(t) + N(0, noise_std), 0, 1)
```

Parameter ranges are randomized per seed within physically plausible bounds and tuned so a readable episode is 60–180 simulated seconds. Fixed-step integration (`dt = 0.1 s`), deterministic given the seed. Clamp physical bounds; log any attempted unsafe command.

**Disturbance families** (hidden mechanism, operator-selectable by name only in the UI):

- `pump_derate`: `eff(t)` drops 25–40% at `t_dist`.
- `extra_leak`: `leak_extra(t)` steps up at `t_dist` so steady-state at the old duty falls well out of band.
- `drain_shift` (optional): `drain_coeff` increases 30–50%.

**Seed separation:** exploration seeds `1–20`; held-out evaluation seeds `1000–1019`; disturbance suite seeds `2000–2009`. Only the evaluator touches the 1000s and 2000s. A test asserts the agent-visible projection never contains them.

### 5.2 Plant B (stretch only): thermal chamber

Heater duty `u` warms a chamber losing heat to ambient. Same normalized observation (`level` renamed `y` in the generic schema, 0–1 normalized), same tool API, same prompts. Hidden params: thermal mass, heater power, loss coefficient, ambient, sensor lag, noise. Disturbance: ambient drop or heater derating. The point is to run the *identical* orchestrator and prompts and show a fresh discovery episode.

Make the agent-facing observation schema plant-agnostic from day one: `{"y": float, "target": float, "dt": float, "elapsed_s": float, "u_range": [0,1]}` plus a short public `plant_description` string ("a reservoir whose level you can raise with a pump; it drains on its own"). The description names the physical domain but no parameters.

### 5.3 Goal and constraints (demo defaults, not certifications)

```yaml
objective:
  target: 0.60
  band: [0.55, 0.65]
  maximize_time_in_band: true
  minimize_tracking_error: true
  minimize_actuation_energy: true
constraints:
  u_range: [0.0, 1.0]
  soft_high_limit: 0.85          # agent is told this
  hard_cutoff: 0.90              # supervisor forces u=0; agent is told this exists
  sensor_timeout_s: 3.0
  max_single_experiment_s: 20
  max_exploration_experiments: 12
  max_controller_candidates: 5
  max_model_calls_per_run: 40
  max_wall_clock_min_per_run: 12
  safe_fallback_u: 0.0
```

Separate the *safety envelope* (trusted code) from the *performance target* (what Muse optimizes). Muse can never loosen the envelope.

### 5.4 Metrics (frozen in `evaluation/config.py` before any scoring run)

| Metric | Definition | Direction |
|---|---|---|
| MAE | `mean(abs(h_true - target))` over scored window (after settling window `t_settle`) | lower |
| In-band fraction | share of scored steps with `h_true` in band | higher |
| Actuation energy | `sum(u_applied**2 * dt)` per episode | lower at comparable MAE |
| Override count | steps where supervisor changed the requested `u` | zero |
| Hard violations | steps where `h_true >= hard_cutoff` | zero |
| Invalid outputs | NaN/Inf/out-of-range/exception from controller | zero |
| Adaptation latency | simulated seconds from `t_dist` to first sustained 10 s in band | lower |
| Controller complexity | source lines, branches (report only) | report |
| Agent budget | model calls, tokens, estimated USD, experiments, wall time | report |

Scoring uses simulator truth `h_true`; the agent only ever sees noisy `y`. Report aggregates over predetermined seeds and keep failed episodes in the tables.

---

## 6. The autonomous discovery and repair loop (the core)

### 6.1 Stage machine

```text
NEW -> EXPLORING -> HYPOTHESIZING -> GENERATING -> STATIC_CHECK -> SANDBOX_CHECK
    -> EVALUATING -> {REVISING -> GENERATING | DEPLOYABLE | FAILED}
DEPLOYABLE -> MONITORING -> {ADAPTING -> GENERATING | COMPLETE}
any -> STOPPED (operator stop or e-stop)
```

Every transition is persisted with timestamp, trigger, and the agent output that caused it. No silent retries. Budgets are checked at every transition.

### 6.2 Agent interaction design: stage-driven structured calls

**Decision:** drive the loop from the orchestrator and ask Muse one structured question per stage, using Chat Completions with `response_format: {type: "json_schema"}` (constrained decoding, conformance guaranteed by the API). Keep the model-driven tool-calling loop as a documented upgrade path behind the same `MuseClient` interface.

Why: Meta's Chat Completions supports only `tool_choice: "auto"`, so a free tool loop cannot force the model to act, and reasoning does not carry across Chat Completions turns. A stage-driven design gives deterministic control flow, guaranteed-parseable outputs, and still leaves every *decision* (which experiment, when to stop exploring, what code, what change) to Muse. Each call receives the complete agent-visible history, so no context is lost between stages.

Stage schemas (Pydantic, mirrored to JSON schema with `additionalProperties: false`):

```python
class Hypothesis(BaseModel):
    id: str                      # "H1"
    statement: str               # "Actuator responds with a lag of several seconds"
    confidence: float            # 0..1
    evidence_refs: list[str]     # experiment ids

class ExperimentProposal(BaseModel):
    hypotheses: list[Hypothesis]             # full current ledger, revised
    uncertainty_targeted: str
    command_u: float                          # within u_range
    duration_s: float                         # <= max_single_experiment_s
    safety_argument: str                      # why this stays under soft limit
    expected_observation: str
    ready_to_generate: bool                   # Muse decides when exploring is enough
    readiness_justification: str              # required; trusted code also enforces >= 3 completed experiments
    operator_note: str                        # one plain-English sentence for the timeline

class ControllerSubmission(BaseModel):
    machine_card: str            # Muse's plain-language summary of what it learned
    design_rationale: str
    source_code: str             # complete Python module defining control(obs, state)
    predicted_behavior: str
    self_test_expectations: list[str]
    operator_note: str

class RevisionSubmission(ControllerSubmission):
    diagnosis: str               # causal explanation of the measured failure
    diagnosis_category: Literal["actuator_weaker", "outflow_increased", "sensor_changed", "unknown"]
    change_summary: str          # what changed in the code and why
    parent_version: str
```

The orchestrator validates every field again in trusted code (ranges, duration, budget). A schema-valid answer is not a safe answer.

**Verified Oct 31 by live calls:** both models return schema-valid JSON for this nested schema with `strict: true` and `additionalProperties: false` on every object (including `$defs`). Spark declared readiness with zero experiments; hence `readiness_justification` and the trusted minimum-experiment rule. `reasoning_effort` is accepted on Chat Completions and reasoning tokens are reported in `usage`; log them.

### 6.3 Agent-visible projection

A single function `session.agent_view()` builds everything the model is allowed to see:

- Public plant description, objective, constraints (including that a hard cutoff exists at 0.90 and that the supervisor will force `u=0` there).
- Experiment summaries: `{id, u, duration_s, t_start, samples: [(t, y)], notes}` downsampled to ≤ 60 points each.
- Hypothesis ledger as last revised by Muse.
- Candidate reports: metrics table, pass/fail per gate, and *agent-safe* failure traces: `(t, y, target, u_requested, u_applied, override_flag)` downsampled. Never `h_true`, never seed ids, never disturbance names.
- Budget remaining.

`tests/test_agent_blindness.py` serializes the view for many runs and asserts no hidden parameter names, numeric parameter values, seed ids in the hidden ranges, or disturbance mechanism names appear.

### 6.4 Exploration safety

- Each proposal is bounded: `0 <= u <= 1`, `0 < duration_s <= 20`, cumulative exploration time and energy capped.
- **Worst-case forward bound:** before approval, the supervisor simulates the proposal against a *conservative envelope model* (max plausible inflow, zero outflow, no lag) from the current measured level. If the bound crosses `soft_high_limit`, reject with reason; Muse may re-propose. The envelope model is trusted code and deliberately crude.
- During any experiment, if `y >= hard_cutoff` or sensor is stale: force `u=0`, mark experiment invalid, record override.
- Model request failure or timeout: no actuator action is taken. Budget decrements.
- Muse cannot weaken any guard. Attempts are logged as events and shown in the UI (they are evidence too).

### 6.5 Controller contract: real code, not a disguised template

```python
# Muse-authored. Required interface. No imports allowed except `math`.
def control(obs: dict, state: dict) -> tuple[float, dict]:
    """
    obs   = {"y": float, "target": float, "dt": float, "elapsed_s": float}
    state = JSON-serializable dict, empty on first call; return the updated dict.
    Return (u in [0, 1], state). No I/O, no randomness, no wall clock, no globals.
    """
```

- Source is stored **byte-for-byte** at `artifacts/runs/<run_id>/controller_vN.py` with sha256, model id, prompt hash, parent version, and the full redacted request/response.
- `controller_diff_vN_vM.patch` is a unified diff of the stored sources.
- Invalid code is rejected with structured feedback and Muse revises within budget. Trusted code never patches Muse's source. A test asserts the registered bytes equal the model's `source_code` field.

**Baselines are not templates:** `evaluation/baselines.py` holds a fixed PID and a fixed on/off controller for *scoring comparison only*. They are never shown to Muse, and a test asserts no baseline source ever appears in a prompt.

### 6.6 Isolation (Docker is available locally)

Static checks (AST): exactly one top-level `control` function; only `math` import; forbid `import`, `exec`, `eval`, `open`, `__import__`, attribute access on dunder names, `global`, `nonlocal`, comprehensions over builtins like `globals()`; cap source at 400 lines. These are defense-in-depth, not the sandbox.

Sandbox: run candidates in a disposable container (`python:3.12-slim`) with `--network none`, `--read-only`, `--user 65534`, `--cap-drop ALL`, `--memory 256m`, `--pids-limit 64`, `--cpus 1`, a hard wall-clock timeout, no mounted secrets. The runner feeds obs via stdin as JSON lines and reads `(u, state)` lines back; the evaluator and simulator run *outside* the container. Docker is also used for the fast evaluation loop by keeping one container alive per candidate for the duration of its suite.

Fallback if Docker is unavailable on a given machine: a `subprocess` with `python -I -S`, restricted builtins, and resource limits, **labeled in the UI as "reduced isolation, dev only"**. Never run the fallback for a public demo or on the Pi.

### 6.7 Orchestrator (to become real code with finite budgets and resumable state)

```python
async def discover_and_control(run: Run, agent: MuseClient, plant: PlantAdapter,
                               safety: Supervisor, evaluator: Evaluator, registry: Registry):
    session = Session.create(run)
    while session.experiments_left() and not session.ready_to_generate:
        proposal = await agent.propose_experiment(session.agent_view())
        verdict = safety.validate_proposal(proposal, plant.observe())
        result = plant.run_bounded(verdict.approved) if verdict.ok else rejected(verdict)
        session.record_experiment(proposal, verdict, result)

    parent = None
    for _ in range(run.limits.max_controller_candidates):
        sub = await agent.author_or_revise(session.agent_view(), parent)
        cand = registry.persist_immutable(sub, parent, run.id)
        static = validator.static_check(cand)
        iface = sandbox.interface_tests(cand) if static.ok else None
        report = evaluator.score(cand, suite="heldout") if iface and iface.ok else failed(static, iface)
        session.record_candidate(cand, static, iface, report)
        if report.meets_release_gate:
            session.transition("DEPLOYABLE", cand.id)
            return await monitor_and_repair(cand, ...)
        parent = cand.id
    session.transition("FAILED")
```

### 6.8 Monitoring, degradation detection, and repair

**Do not stop when v1 passes.** The approved controller enters a monitored rollout.

- `monitor.py` (trusted) computes a rolling 15 s MAE on `y` vs target. Baseline is the rolling MAE from the pre-disturbance segment. Degradation is declared when rolling MAE exceeds `max(2.0 × baseline, 0.05)` for 10 consecutive seconds, or any override occurs. The detector's thresholds are config, logged, and shown in the UI.
- The operator triggers a hidden disturbance via `POST /api/runs/{id}/disturbance {"family": "pump_derate"}`. The *agent* receives only: "performance degraded; here are the traces".
- On degradation → `ADAPTING`: Muse gets v1's source, the pre/post traces, and the metrics, and returns a `RevisionSubmission`. v2 is registered, checked, sandboxed, and scored on the **same disturbance seeds as frozen v1**.
- Promote v2 only if the adaptation gate passes. Otherwise keep v1 deployed, record the failure, allow bounded retries. Never auto-promote a worse or unsafe candidate.

### 6.9 Proving Muse did the work

- Raw Muse sources for ≥ 2 versions with semantic diff, model id, prompt hash, timestamps.
- Distinct Muse-proposed experiments each tied to a named uncertainty in the ledger.
- The blindness test and the agent-view JSON exported per run.
- **Ablation:** same budget, v1 frozen through disturbance (no revision) vs full Praxion vs fixed PID vs on/off.
- Honest baseline reporting: if PID wins, say so.
- All prompts and completions stored redacted under `artifacts/runs/<id>/model_calls.jsonl`.

---

## 7. Meta Model API integration (verified Oct 30, 2026)

### 7.1 Facts

| Item | Verified value |
|---|---|
| Base URL | `https://api.meta.ai/v1` (OpenAI SDK). Anthropic SDK: `https://api.meta.ai`. |
| Auth | `MODEL_API_KEY` as Bearer. The OpenAI SDK does not read it automatically; pass it explicitly. |
| Primary model | `muse-wonder-1.0` (preview). Most capable; long-horizon agentic work. $4.00 / $20.00 per 1M in/out; cached input $0.20. |
| Fallback model | `muse-spark-1.3` (recommended for new work). $1.25 / $4.25 per 1M; cached $0.15. |
| Avoid | `*-contributor` variants: Meta may train on content. Not for a hackathon demo. |
| Context | 1,048,576 tokens on Wonder and Spark. |
| Rate limits | 3,000 RPM, 4M TPM per team. Retry 429 with exponential backoff and jitter; honor `Retry-After`. |
| Protocols | Responses `POST /v1/responses` (recommended, reasoning continuity), Chat Completions `POST /v1/chat/completions`, Messages `POST /v1/messages`. |
| Tool calling | Chat Completions: `tools=[{"type":"function","function":{...}}]`; only `tool_choice="auto"`; tool results as `{"role":"tool","tool_call_id":..., "content": str}` after appending the assistant message. |
| Structured output | Chat Completions: `response_format={"type":"json_schema","json_schema":{"name":..., "schema":{...}}}`, constrained decoding. Responses API: `text.format` instead (sending `response_format` there is a 400). No recursive `$ref`. |
| Pydantic helper | `client.beta.chat.completions.parse(..., response_format=Model)` → `.parsed`. |

Not needed for the MVP: SAM 3.1, Muse Image, Muse Voice. Do not spend time on them.

### 7.2 Cost envelope

A full run ≈ 12 experiment calls + 5 candidate calls + 3 revision calls ≈ 20–25 calls, each ~10–20k input tokens (history grows) and ~2–4k output. Roughly 0.4M in / 0.08M out → **≈ $3 per run on Wonder, ≈ $0.85 on Spark.** Fifty development runs on Spark cost less than a lunch. Use Spark for iteration, Wonder for the recorded demo and benchmarks, and log which model produced every artifact.

### 7.3 Smoke test (`scripts/check_meta.py`)

```python
import os
from openai import OpenAI

client = OpenAI(base_url=os.getenv("META_BASE_URL", "https://api.meta.ai/v1"),
                api_key=os.environ["MODEL_API_KEY"])
r = client.chat.completions.create(
    model=os.getenv("MUSE_MODEL", "muse-spark-1.3"),
    messages=[{"role": "user", "content": "Reply exactly: ready"}],
)
print(r.model, "|", r.choices[0].message.content, "|", r.usage)
```

### 7.4 Environment

```dotenv
MODEL_API_KEY=                        # never commit
META_BASE_URL=https://api.meta.ai/v1
MUSE_MODEL=muse-wonder-1.0            # muse-spark-1.3 for dev iteration
MUSE_FALLBACK_MODEL=muse-spark-1.3
PRAXION_MODE=sim                   # sim | pi
PRAXION_AGENT_MODE=live            # live | replay | mock
PRAXION_SANDBOX=docker             # docker | subprocess_dev_only
MAX_MODEL_CALLS_PER_RUN=40
MAX_EXPERIMENTS_PER_RUN=12
MAX_CONTROLLER_CANDIDATES=5
MODEL_TIMEOUT_SECONDS=120
```

`mock` is for CI and must be visibly labeled everywhere. `replay` plays a recorded live run at original pacing and is labeled "REPLAY of run <id>, recorded <timestamp>, model <id>". A demo that claims to be live must be live.

---

## 8. Repository layout, API, storage

One Python service, one small frontend. No Kubernetes, queues, or microservices.

```text
praxion/                               # repo (product name: Praxion)
├── CLAUDE.md                          # operating rules for Claude (authoritative)
├── PRAXION_IMPLEMENTATION_PLAN.md  # this document
├── README.md                          # setup, one-command eval, demo, claims
├── pyproject.toml                     # uv-managed; python 3.12
├── .env.example
├── backend/
│   ├── main.py                        # FastAPI: REST + SSE
│   ├── config.py
│   ├── schemas.py                     # Pydantic: observations, proposals, submissions, reports
│   ├── agent/
│   │   ├── muse_client.py             # provider adapter, retries, usage/cost logging, redaction
│   │   ├── prompts.py                 # versioned prompts + hash
│   │   ├── orchestrator.py            # stage machine, budgets, resumable session
│   │   ├── view.py                    # agent_view(): the only path from trusted data to the model
│   │   └── mock_agent.py              # CI only; clearly labeled
│   ├── plant/
│   │   ├── base.py                    # PlantAdapter protocol
│   │   ├── tank_sim.py                # hidden dynamics (P0)
│   │   └── thermal_sim.py             # stretch only; not scheduled
│   ├── safety/
│   │   ├── supervisor.py              # final authority over u_applied; override logging
│   │   └── envelope.py                # conservative worst-case forward bound
│   ├── controller/
│   │   ├── registry.py                # immutable versions, sha256, parent, diff
│   │   ├── static_check.py            # AST rules
│   │   ├── sandbox.py                 # docker runner + dev fallback
│   │   └── runtime.py                 # fixed-rate trusted loop around an approved candidate
│   ├── evaluation/
│   │   ├── config.py                  # frozen metrics, windows, seeds, gates
│   │   ├── suite.py                   # heldout + disturbance suites, same-seed comparisons
│   │   ├── metrics.py
│   │   ├── monitor.py                 # degradation detector
│   │   └── baselines.py               # PID + on/off (scoring only, never prompted)
│   └── storage/
│       ├── db.py                      # SQLite
│       └── artifacts.py               # JSONL + files per run
├── frontend/                          # Vite + React + Recharts + diff viewer
├── scripts/
│   ├── check_meta.py
│   ├── run_live_demo.py               # full loop, records a replayable run
│   ├── run_evaluation.py              # scores all variants on frozen seeds → docs/BENCHMARKS.md tables
│   ├── replay_run.py
│   └── export_artifacts.py
├── tests/
├── docs/
│   ├── IMPLEMENTATION_STATUS.md       # living: done / verified / blocked / repro commands
│   ├── SAFETY_LIMITATIONS.md
│   ├── DEMO_SCRIPT.md
│   ├── BENCHMARKS.md                  # generated tables, including failures
│   └── archive/                       # superseded Codex plan
└── artifacts/
    ├── samples/<run_id>/              # committed exemplar runs (redacted)
    └── runs/<run_id>/                 # gitignored working runs
        ├── event_log.jsonl
        ├── experiments.json
        ├── hypothesis_ledger.json
        ├── machine_card.md
        ├── controller_v1.py
        ├── controller_v2.py
        ├── controller_diff_v1_v2.patch
        ├── model_calls.jsonl           # redacted prompts/completions, usage, cost
        ├── agent_view_snapshots/
        ├── evaluation.json
        ├── metrics.csv
        ├── rollout.png
        └── report.md
```

### API

| Method | Route | Purpose |
|---|---|---|
| `POST` | `/api/runs` | Create run: plant, goal, limits, label, agent mode |
| `POST` | `/api/runs/{id}/start` | Start bounded discovery loop; idempotent |
| `GET` | `/api/runs/{id}` | Stage, selected controller, headline metrics, budget |
| `GET` | `/api/runs/{id}/events` | SSE stream of stage transitions, experiments, model calls, scores |
| `GET` | `/api/runs/{id}/controllers` | Versions, metadata, diffs |
| `GET` | `/api/runs/{id}/metrics` | Seed-level and aggregate evaluation |
| `GET` | `/api/runs/{id}/ledger` | Hypothesis ledger history and machine card |
| `POST` | `/api/runs/{id}/disturbance` | Trigger hidden plant change by family name |
| `POST` | `/api/runs/{id}/stop` | Stop; force neutral actuator |
| `GET` | `/api/runs/{id}/export` | Zip of the artifact bundle |
| `GET` | `/health` | Service, sandbox mode, provider, model |

`/disturbance` tells the agent nothing about the mechanism. Only the UI operator and the evaluator know.

### Storage

SQLite tables: `runs, experiments, observations, hypotheses, candidates, evaluations, agent_events, model_calls`. JSONL event log is the portable source of truth; SQLite indexes it for the UI.

---

## 9. Validation pipeline and safety supervisor

Candidate pipeline, in order, each step recorded:

1. **Registry:** persist bytes, hash, parent, model id, prompt hash.
2. **Static check:** AST rules (6.6). Fail → structured feedback to Muse.
3. **Sandbox interface tests:** cold start, empty state, state round-trip through JSON, NaN/Inf/negative `dt` inputs, repeated calls, out-of-range guard, 10k-call timing budget, determinism (same inputs → same outputs).
4. **Held-out suite:** 10 episodes on seeds 1000–1009, nominal dynamics.
5. **Disturbance suite (for v2 and ablation):** 5 episodes on seeds 2000–2004 with the active disturbance family, same seeds for v1 and v2.
6. **Safety accounting:** any hard violation → candidate marked unsafe, never approved. Override count is scored against the candidate.
7. **Compare and gate:** against baselines and parent version.
8. **Promote or reject:** record; rollback is always possible.

**Trusted supervisor** owns `u_applied`:

```text
if sensor_invalid or stale or emergency_stop or y >= hard_cutoff:
    u_applied = 0.0, reason = ...
else:
    u_applied = clamp(u_requested, 0, 1)
log (t, u_requested, u_applied, reason)
```

A forced safe stop never counts as the controller obeying constraints.

---

## 10. Gates, benchmarks, ablation (frozen before scoring)

Proposed engineering acceptance criteria, not results.

**Gate 0 — Foundation.** Real key connects; simulator deterministic under seed; baselines control the plant; UI shows stored events only; tests pass.

**Gate 1 — Authentic discovery.** In a live run, Muse proposes ≥ 3 distinct bounded experiments tied to ledger entries, receives measurements, revises the ledger, and authors ≥ 1 statically valid controller saved verbatim.

**Gate 2 — Controller performance.** On ≥ 8 of 10 held-out episodes: finite valid commands, zero hard violations, zero overrides, ≥ 70% in-band after `t_settle` (frozen in config, suggested 30 s of a 120 s episode).
*Stretch:* beat the transparent fixed PID by ≥ 15% median MAE with no worse safety or energy. If PID wins, report it.

**Gate 3 — Self-repair (the judge moment).** v1 frozen; hidden disturbance; Muse sees only measurements; authors v2 with a meaningful code change. On ≥ 3 of 5 disturbance episodes, v2 reduces post-disturbance MAE by ≥ 20% vs frozen v1 with zero hard violations.

**Gate 3b — Transfer (stretch).** Fresh run on the thermal plant with unchanged orchestrator and prompts passes Gate 1 and Gate 2 thresholds.

**Ablation table (required in `docs/BENCHMARKS.md`):**

| Variant | Experiments | Writes controller | Revises after failure |
|---|---|---|---|
| Fixed PID | no | no | no |
| Fixed on/off | no | no | no |
| Muse v1 frozen | yes | yes | no |
| Full Praxion | yes | yes | yes |

Columns: MAE, in-band %, energy, overrides, hard violations, adaptation latency, model calls, cost, wall time. Raw per-seed rows plus medians. Confidence intervals only if run counts justify them.

If a gate fails, present the measured failure and scope the demo to what actually works.

---

## 11. Frontend and demo

Single desktop page, four panels, all wired to real backend state:

1. **Plant:** level vs time, shaded band, soft/hard limit lines, pump duty overlay, disturbance marker, badge `SIMULATED` / `REPLAY` / `HARDWARE`.
2. **Agent timeline:** Hypothesize → Experiment → Observe → Author v1 → Test → Degrade → Diagnose → Author v2 → Re-test, each with timestamp, model id, operator note, and expandable raw JSON. Hypothesis ledger shown as a confidence table that updates per experiment.
3. **Controller code:** v1 / v2 side-by-side diff, hash, model, static/sandbox/eval status, machine card.
4. **Evidence:** v1 vs v2 on the same disturbance seed, metric table with baseline row, gate pass/fail chips, budget and cost.

Controls: `Start Discovery`, `Introduce Disturbance ▾ (family)`, `Compare Versions`, `Stop`, `Export Evidence`, `Compare Baselines`. Disabled controls state their prerequisite.

### Three-minute demo script

- **0:00–0:20 Hook.** "This machine has no manual, no model, no controller. Praxion will learn it and write one."
- **0:20–0:55 Discover.** Muse's first hypotheses, experiment proposals, the tank responding, the ledger confidences moving.
- **0:55–1:25 Build.** `controller_v1.py` appears, hashed, sandboxed, scored on hidden seeds. Machine card in Muse's words.
- **1:25–2:05 Break.** Press Introduce Disturbance. Error climbs. Degradation detector fires. Muse diagnoses from traces and emits a visibly different `controller_v2.py`.
- **2:05–2:40 Prove.** Same-seed v1 vs v2 charts, metric table with PID baseline, zero violations, ablation.
- **2:40–3:00 Reach.** Show the ablation table and the N-run distribution: this is a protocol, not a lucky run. State plainly that simulation does not establish real-world safety.

If live latency is unreliable, present a replay of a real recorded run and say so on screen.

---

## 12. Phases, exit criteria, and the iteration loop

Phases exit on evidence, not on dates. The calendar is a budget: Oct 31 → Nov 4, submit by 6 PM ET Nov 4.

| Phase | Builds | Exit criterion (all must hold) | Budget |
|---|---|---|---|
| **0 Ground truth** | `uv` scaffold; `TankSimulator` with seeded hidden params and disturbance hooks; `PlantAdapter`; supervisor + envelope; metrics + frozen `evaluation/config.py`; PID + on/off baselines; static checker; Docker sandbox runner; hostile corpus | tests green; determinism test; baselines hold band on exploration seeds; sandbox blocks every hostile candidate; real API reply recorded | Oct 31 |
| **1 Discovery → v1** | `MuseClient` (structured, retries, cost, redaction); prompts v1 with readiness gating; `agent_view()` + blindness test; orchestrator NEW→EVALUATING; registry; evaluator held-out suite + gates; artifact bundle; mock agent for CI | one live run produces a scored, hashed `controller_v1.py` bundle; blindness test passes on its snapshots | Oct 31 – Nov 1 |
| **2 Break → repair** | monitor with logged thresholds; disturbance families; ADAPTING stage with diagnosis category; same-seed v1/v2/baseline comparison; ablation runner; `run_evaluation.py` → `BENCHMARKS.md` | Gate 3 measured and recorded (pass or fail); diagnosis accuracy recorded | Nov 1 – Nov 2 |
| **3 Evidence surface** | FastAPI + SSE; dashboard (plant, timeline + ledger, diff, evidence); replay; export | UI renders only stored events; a recorded run replays faithfully with labels | Nov 2 |
| **4 Depth iteration** | N ≥ 5 live runs per protocol version; failure-mode analysis; improvements to protocol / prompts / view / traces; re-run; `BENCHMARKS.md` distribution | best measured distribution achieved under the frozen evaluator; every weakest link fixed or documented | Nov 2 – Nov 3 |
| **5 Ship** | README; SAFETY_LIMITATIONS; DEMO_SCRIPT; 3-min video from a real run; clean-clone repro; public repo; secrets scan; provenance | submitted ≥ 3 h early | Nov 4 |

### The iteration loop inside every phase

```text
brief (Fable) → build (Opus) → run tests (Fable) → review diff (Fable)
   → fail: return precise defects to the same agent → rebuild
   → pass: depth review → record in IMPLEMENTATION_STATUS.md → next item
```

### Depth review template (written at every phase exit)

1. **What did this phase prove, with which command or artifact?**
2. **What would a skeptical control engineer say is fake, lucky, or leaked?**
3. **What is the single weakest link?** Fix it before adding anything.
4. **What did we learn that changes the plan?** Record the decision.

### Stop/go rules

If live Muse cannot produce schema-valid, safe proposals after prompt iteration → switch to Spark, simplify schemas, fix before anything else. If no live run yields a scored v1 by end of Nov 1 → freeze UI work. If v2 is worse than v1 → keep the truthful result and iterate the protocol (experiment informativeness, failure traces, diagnosis prompt), never the output or seeds. Phase 4 runs on Spark for iteration and on Wonder for the recorded distribution.

---

## 13. Hardware

Out of scope for this submission (decided Oct 31). The `PlantAdapter` interface is the only hardware seam; nothing else in the design assumes a simulator. Any future physical deployment requires its own validation, an independent hardware interlock, and never executes model-authored Python unsandboxed.

---

## 14. Test checklist

**Unit**

- [ ] Simulator traces reproducible under fixed seed (tolerance 1e-9).
- [ ] `u<0`, `u>1`, NaN/Inf, negative duration, missing readings rejected by supervisor.
- [ ] Hard cutoff forces `u=0` and records override.
- [ ] Envelope bound rejects proposals that could cross the soft limit.
- [ ] Agent view contains no hidden params, seeds, disturbance names, baseline source (blindness test).
- [ ] Controller state round-trips through JSON.
- [ ] Static checker rejects imports, exec/eval, dunder access, file/network/process access.
- [ ] Sandbox denies network, filesystem writes, and enforces timeouts (test with hostile candidates).
- [ ] Registry stores bytes identical to the model's `source_code` field; hash and parent recorded.
- [ ] Metrics match hand-computed values on a synthetic trace.
- [ ] Degradation detector fires on a synthetic step change and not on nominal noise.

**Integration**

- [ ] Mock agent exercises the full loop in CI, labeled mock, zero API spend.
- [ ] Live smoke test marked `live`, skipped without key.
- [ ] Live run: ≥ 3 experiments with telemetry; Muse source saved as `controller_v1.py`.
- [ ] Bad candidate → structured feedback → revised candidate (no silent patching).
- [ ] Disturbance produces measurable deviation on frozen v1.
- [ ] v2 scored on the same seeds as v1.
- [ ] Network failure halts experiments but not the supervisor or runtime.
- [ ] Replay reproduces the recorded timeline and is labeled as replay.

**Release**

- [ ] Public repo, license, provenance statement (new work Oct 26 – Nov 4), `.env` excluded, secrets scan clean.
- [ ] README: setup, one-command evaluation, one-command replay, claims and non-claims.
- [ ] `BENCHMARKS.md` has per-seed rows including failures, with model ids.
- [ ] Video matches stored artifacts; replay sections labeled.
- [ ] `SAFETY_LIMITATIONS.md` states what is and is not established.

---

## 15. Prompt contracts (store versioned in `backend/agent/prompts.py`, hash saved with each artifact)

**Discovery system contract**

> You are an experimental control engineer working with an unknown physical system. You interact only through the provided observations and bounded experiments. Your goal is to learn how the system responds to its single input with as few experiments as possible, then author a control policy that meets the objective within the stated constraints. Maintain an explicit hypothesis ledger with confidences. For each experiment state the uncertainty it reduces, the expected observation, and why it is safe under the soft limit. Never claim knowledge of the true model, hidden parameters, or future test scenarios. Never request exceptions to safety limits. If evidence is insufficient, request another bounded experiment rather than inventing physics. Set `ready_to_generate` only when you can justify a controller design from the evidence.

**Controller authoring contract**

> Using the documented `control(obs, state)` interface and only the evidence in this session, write a complete new controller module. Only `import math` is permitted. No file, network, environment, process, randomness, wall clock, or global state. Return bounded finite actions and a JSON-serializable state dict. Design for the lag, gain, and disturbance behavior you actually observed; prefer robustness over aggressiveness. Write a machine card summarizing in plain language what you learned about this system. Do not declare success; the independent evaluator decides.

**Repair contract**

> The deployed controller degraded in the measured ways shown. Diagnose at least one plausible causal explanation from the traces. Produce a meaningful code change targeted at that diagnosis, predict how behavior should change, and return the complete revised module. The evaluator, not your explanation, decides whether the repair worked. Stay within all safety limits.

---

## 16. Positioning for judges

**Title:** Praxion — a self-discovering control engineer for physical machines.

**Description:** Meta Muse learns a machine's dynamics from bounded experiments, writes an executable controller, verifies it in a sandbox against hidden scenarios, and repairs its own code when the machine's behavior changes. The same protocol runs unchanged on a second plant family. A reusable interface like this could one day retrofit simple equipment with adaptive, auditable control.

**Precise innovation claim:** an agentic control-engineering pipeline linking hypothesis formation, active experimentation, model-authored code, independent safety validation, and self-repair, demonstrated on held-out black-box simulations across two plant families.

**Do not claim:** works on any machine; guaranteed safety; Muse "learned physics from scratch"; AI beats PID (unless same-seed data says so); Pi deployed (unless done).

**One sentence:** "We handed Muse an unknown machine, let it run only safe experiments, watched it write a working controller, changed the machine, and watched Muse repair its own code, with the measurements and diffs to prove each step."

---

## 17. References

- Hackathon: https://events.cerebralvalley.ai/e/meta-ai-developer-hackathon (Official Rules linked from the event dashboard; confirm submission format there)
- Meta Model API overview: https://dev.meta.ai/docs/overview
- Models: https://dev.meta.ai/docs/models
- Pricing and rate limits: https://dev.meta.ai/docs/pricing-rate-limits
- Protocols: https://dev.meta.ai/docs/protocols
- Structured output: https://dev.meta.ai/docs/cookbook/structured-output
- Tool calling: https://dev.meta.ai/docs/cookbook/tool-function-calling
- SDKs: https://dev.meta.ai/docs/sdks
- API reference: https://dev.meta.ai/docs/api-reference

---

## 18. Kickoff instruction for Claude

> Read `CLAUDE.md` and `PRAXION_IMPLEMENTATION_PLAN.md` in full. Build Praxion in P0 order: `uv`-managed Python 3.12 project, deterministic hidden-parameter tank simulator, PlantAdapter, trusted safety supervisor with envelope bound, metrics and frozen evaluation config, PID and on/off baselines, `scripts/check_meta.py`, then the Muse client with structured outputs, prompts, orchestrator stages, registry, static checker, Docker sandbox, agent view with blindness test, evaluator suites and gates, monitor and disturbance, repair stage, FastAPI + SSE, dashboard, replay, ablation runner, benchmarks. Run tests after every module. Make one real Muse call as soon as the key exists and record the result in `docs/IMPLEMENTATION_STATUS.md`. Never fake an output. Never hand-write the demo controller. Keep everything ready for a public repo.
