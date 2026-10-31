# WorldPatch — Autonomous Physical Controller Discovery

**Codex implementation specification | Meta Global AI Developer Hackathon (2026)**  
**Track:** Push the Frontier (Indie Developer, if solo)  
**Hackathon submission deadline:** November 4, 2026, 9:00 PM Eastern Time  
**Project status:** Proposed engineering design; no claims of proven model performance  
**Primary runtime:** Python 3.11+, Meta Model API, FastAPI, React/Vite or Next.js  
**MVP 1:** Pure simulation, essential  
**MVP 2:** Raspberry Pi + low-voltage water-level apparatus, optional after MVP 1 works

---

## 0. Instructions to Codex — read this first

You are the lead implementation engineer. **Build a working, reproducible proof of concept, not a slide deck or a chat UI pretending to control a machine.** Implement the sections below in priority order. Work autonomously, make sensible choices, run tests, correct issues, and record outstanding blockers in `docs/IMPLEMENTATION_STATUS.md`. Do not invent successful API responses, benchmark results, controller improvements, or hardware tests.

**Hard priorities**

1. The **Muse-powered discovery → experiment → controller-code generation → simulation test → self-revision** loop must work end-to-end. This is the heart of WorldPatch.
2. Keep the plant parameters hidden from the **runtime Muse agent**. The Codex development process will necessarily see simulator source; the *agent being evaluated* must receive only permitted sensor observations, actuator metadata, and experiment outcomes—not true dynamics, parameter seeds, reference solutions, or hidden evaluation scenarios.
3. A generated controller must be a **new versioned executable policy authored by Muse**, not merely a selection among pre-written PID controller templates. It may implement PID, feed-forward, hysteresis, adaptive logic, or something else, but the algorithm/code must originate in a model response and pass independent validation.
4. No generated code executes directly on the host without isolation. No model writes directly to GPIO. Independent safety checks always have final authority.
5. The UI must expose **actual** experiments, generated source-code differences, observed performance, and failures; avoid deceptive scripted playback.
6. Deliver MVP 1 before attempting MVP 2. Hardware, SAM, video interpretation, model fine-tuning, a second plant family, complex RL, and elaborate styling are stretch work.
7. The public repository must clearly identify new hackathon work; provide a reproducible three-minute demo and accurate results.

**Definition of a successful project:** A previously unseen simulated physical plant is observed via a restricted tool interface. Muse chooses informative safe experiments, uses the observations to propose and author a controller, tests that controller against hidden scenarios, and changes the code after discovering a mismatch. The final system produces an auditable artifact and proves behavior with measurements.

**Definition of an unsuccessful project:** The model only describes telemetry; a developer secretly hard-codes the successful controller; the model gets plant parameters or hidden test outcomes; improvements are asserted without quantitative evidence; or an unverified code artifact is deployed to hardware.

---

## 1. Vision and differentiator

### One-sentence pitch

> **WorldPatch gives unfamiliar physical machines a small adaptive brain: Meta Muse designs safe experiments, learns how a machine responds, writes a controller, tests it, and repairs the controller when the machine changes.**

### The central technical hypothesis

A general-purpose agent connected to an intentionally restricted physical-system interface can autonomously discover enough about an unfamiliar dynamical system to create a useful control policy and adapt it after a disturbance **without being given a machine-specific controller**.

**What this is not:** proof that any machine can safely be automated, a novel invention of PID control/system identification, universal zero-shot industrial automation, certified safety controls, or evidence of production readiness. The hackathon demonstrates an *agentic engineering workflow*, not universal physical autonomy.

### Meta-model contribution must be essential

Muse must perform all four observable reasoning tasks:

1. **Hypothesize:** Describe what could explain the machine's response and what remains uncertain.
2. **Experiment:** Choose bounded inputs and durations to distinguish competing hypotheses.
3. **Synthesize:** Author a complete, executable controller function based on real observations.
4. **Revise:** Use failure traces and measured controller performance to generate a *meaningfully changed controller*, and explain the change.

The ordinary Python components may simulate physics, fit statistics, enforce limits, and measure performance. They may **not** substitute a hidden expert controller and call it Muse.

### Judges should immediately see

- Unknown machine → no controller exists.
- Muse proposes an experiment; the simulator moves; measurements appear.
- Muse writes `controller_v1.py`; the test graph shows what works and fails.
- An abrupt change is introduced; prediction and tracking error increase.
- Muse creates a visibly different `controller_v2.py`; re-test and compare.
- One artifact bundle contains both controller versions, agent decisions, model usage, safety checks, and benchmark evidence.

---

## 2. MVP boundaries

| Capability | MVP 1: simulation (P0) | MVP 2: Raspberry Pi (P1) |
|---|---|---|
| Unfamiliar plant | Seeded black-box water tank | Low-voltage tabletop water reservoir |
| Observe state | `observe()` simulated level | Real water-level sensor readings |
| Operate actuator | `apply_input(u, duration)` | Bounded pump duty commands via guarded driver |
| Discover dynamics | Muse plans bounded experiments | Use same agent protocol with physical observations |
| Write controller | Muse generates Python policy source | Deploy **approved** policy under local supervisor |
| Test controller | Many seeded held-out episodes | Dry run + short bounded physical trials |
| Adapt to change | Hidden leak / pump-efficiency change | Safe manually introduced disturbance, if feasible |
| Visualization | Live graphs, logs, code diff, metrics | Same UI with hardware telemetry mode |
| Offline / degraded mode | Controller continues without Muse | Local controller + hardware interlock only |

**Do not hold up MVP 1 waiting for hardware.** A fully truthful simulation demo with real API calls and an independent evaluator is better than an unreliable physical demo.

### Optional transfer demonstration (P2)

A *second* simulated plant, such as a thermal chamber or motor speed system, with identical tool interfaces and unchanged orchestration code. Run a fresh episode without giving the agent plant-specific code. Only attempt this if primary MVP and evaluations pass.

---

## 3. Single integrated architecture + control-flow diagram

The diagram deliberately merges **design components, the agent feedback loop, generated code, execution safety, simulation/Pi adapters, testing, and outputs**.

```mermaid
flowchart TD
    U[Human goal and constraints<br/>"Keep level at 60%, avoid overflow,<br/>minimize pump energy"] --> UI[Web dashboard / REST API]
    UI --> O[Experiment orchestrator<br/>finite-state workflow + event log]
    O --> M[Meta Muse Wonder 1.0<br/>fallback: Muse Spark 1.3<br/>hypothesize / select experiment / author code / revise]
    M -->|Structured experiment proposal| V[Action validator + safety supervisor<br/>limits / budgets / guards / emergency stop]
    V -->|Approved bounded actuator commands| A[PlantAdapter interface<br/>observe / apply_input / reset]
    A --> S[Simulator adapter<br/>hidden dynamics + noise + disturbances]
    A --> P[Raspberry Pi adapter - OPTIONAL<br/>sensors + low-voltage pump driver]
    S --> T[Telemetry + measurement store<br/>time-series / experiment ID / source]
    P --> T
    T --> O
    M -->|New controller source v1 / v2 / ...| C[Controller artifact registry<br/>source hash / diff / rationale]
    C --> G[Static checks + isolated execution<br/>code validation / strict resources / no network]
    G -->|Candidate passes basic checks| E[Independent evaluator<br/>hidden seeds + disturbance tests + baselines]
    E -->|Pass / fail + measured metrics| O
    E -->|Approved version only| R[Local deterministic controller runtime<br/>fixed-rate actions; no cloud in fast loop]
    R --> V
    T --> D[Charts + experiment timeline + evidence]
    E --> D
    C --> D
    D --> UI
    O -->|budget or test criteria met| F[Final report<br/>result.json + source diff + plots + demo]
    style M fill:#243b55,color:#fff,stroke:#79b2ff
    style V fill:#593e20,color:#fff,stroke:#efbc68
    style G fill:#593e20,color:#fff,stroke:#efbc68
    style E fill:#214d3d,color:#fff,stroke:#65c99f
```

**Two time scales:** The Muse agent operates **between experiments**, with latency on the order of seconds or more; the trusted controller runs at a fixed local interval (e.g. 0.2–1.0 seconds). Cloud availability is never required to maintain an already deployed policy or enforce safety limits.

---

## 4. The unfamiliar plant (the physics Muse must discover)

### The initial challenge: water-level control

A simple reservoir has an adjustable input pump, an uncontrolled outflow, a level sensor, and a target level. Its behavior is initially unknown to the agent. We deliberately choose this system because it is visual, inexpensive, measurable, and transferable to real physical hardware.

**Agent sees:** Target level, allowed pump range, bounded current measurements, past experiments, limits, time, and candidate performance reports.  
**Agent does not see:** Tank cross-section, nominal pump curve, outflow coefficient, actuator lag, measurement noise parameters, hidden disturbance schedule, or test seed.

### Suggested simulator dynamics (internal, *not exposed in agent prompts*)

At simulation time step `dt`:

```text
u_cmd(t) in [0.0, 1.0]
u_actual(t+dt) = clamp(u_actual(t) + (dt/tau)*(u_cmd(t)-u_actual(t)), 0, 1)
q_in = pump_gain * max(0, u_actual - deadband) / max(1e-6, 1-deadband)
q_out = leak_base + drain_coeff * sqrt(max(h, 0)) + disturbance_flow(t)
h(t+dt) = clamp(h(t) + dt*(q_in-q_out)/tank_area, 0, 1)
y(t) = clamp(h(t) + gaussian_noise, 0, 1)
```

Variables `tank_area`, `pump_gain`, `deadband`, `tau`, `drain_coeff`, `leak_base`, noise, disturbances, and initial level are randomized within physically reasonable simulator ranges. **All numeric values are prototype design choices, not claims about a real pump**; tune for a readable 60–180 second demo. Use numerical integration with deterministic seeds; clamp physical bounds and log attempted unsafe commands.

Implement two simulator settings:

- **Plant A / discovery:** Nominal unknown response, low noise, moderate actuator lag.
- **Plant B / unseen disturbances:** Pump efficiency decreases by ~25–40%, or drainage increases. Keep the disturbance hidden until the agent observes changed behavior.

Use **training/exploration seed separation**: e.g. `1–20` for tuning and `1000–1019` for held-out evaluation. The runtime agent must never see the hidden test seeds or parameters.

### Goal and hard constraints

```yaml
objective:
  target_level: 0.60
  acceptable_band: [0.55, 0.65]
  maximize_time_in_band: true
  minimize_tracking_error: true
  minimize_pump_energy: true
constraints:
  action_u_range: [0.0, 1.0]
  high_level_soft_limit: 0.85
  high_level_hard_cutoff: 0.90
  sensor_timeout_seconds: 3.0
  max_single_experiment_seconds: 20
  max_exploration_experiments: 12
  max_controller_candidates: 5
  max_wall_clock_minutes_per_run: 12
  safe_fallback_action: 0.0
```

These values are **demo defaults**, not engineering safety certifications. Separate the *safety envelope* from the *performance target*. The hard cutoff is enforced by trusted code, never controlled by Muse.

### Evaluation metrics (lower or higher as indicated)

- **MAE:** `mean(abs(measured_level - target_level))` over the scored window; lower is better.
- **In-band time:** fraction of time steps where true level is within `[0.55, 0.65]`; higher is better. Use simulator truth for the independent scorer; the agent only sees measured level.
- **Actuation cost:** `sum(u_cmd**2 * dt)` normalized per episode; lower is better at comparable tracking performance.
- **Safety:** hard-limit violation count and invalid actions; **zero required**.
- **Adaptation latency:** simulated seconds from disturbance to regained stable in-band tracking; lower is better.
- **Controller complexity:** lines and number of external dependencies; report only, avoid forcing smaller code at the expense of quality.
- **Agent budget:** number of tool calls, experiment count, cloud model calls, tokens, estimated API spend, elapsed wall time.

Do **not** calculate improvements from a cherry-picked run; report aggregate results over predetermined seeds and keep unsuccessful runs.

---

## 5. Autonomous experiment + discovery loop (the core invention)

### Stage machine

`NEW -> EXPLORING -> HYPOTHESIZING -> GENERATING -> STATIC_CHECK -> EVALUATING -> {REVISING | DEPLOYABLE | FAILED} -> MONITORING -> {ADAPTING | COMPLETE}`

Persist every state transition with a timestamp and agent output. No silent rerun after failure.

### Restricted tools made available to Muse

Expose *only* these safe tools, all mediated by the orchestrator:

```python
observe() -> Observation
propose_experiment(command: float, duration_s: float, reason: str) -> ProposalResult
run_approved_experiment(proposal_id: str) -> ExperimentResult
get_experiment_history(limit: int = 12) -> list[ExperimentSummary]
submit_controller(source_code: str, rationale: str, version_parent: str | None) -> CandidateResult
evaluate_controller(candidate_id: str, suite: str) -> EvaluationReport
get_controller_diff(old_id: str, new_id: str) -> str
finish(summary: str, selected_candidate_id: str | None) -> FinalResult
```

**Never expose:** `get_true_parameters()`, arbitrary shell execution, filesystem access, unrestricted Python REPL, or any operation that bypasses constraints. The agent is given readings and results from bounded physical experiments, not simulated omniscience.

### What counts as genuine experimentation?

A model must explicitly identify an uncertainty, choose an informative test, read its result, and update its hypothesis. Example:

```text
Hypothesis: pump response is delayed or flow gain is weak.
Experiment: apply 0.35 input for 8 seconds while staying below the high-level guard.
Observation: level initially barely moves, then rises gradually.
Inference: actuator has a delay; pure on/off regulation may overshoot.
Next action: test a second bounded input level to distinguish deadband from lag.
```

This is illustrative, not a predicted Muse output. Model outcomes may be incorrect. Save observed traces so judges can inspect the actual reasoning/actions.

### Required constraints on agent exploration

- Limit each action duration, command range, run count, and cumulative time/energy.
- Reject experiments if forward worst-case bounding suggests possible hard-limit violation; a coarse conservative bound is sufficient for MVP.
- If measurement or model request fails, perform no additional actuator action.
- At any hard limit, immediately force `u = 0` and mark the experiment invalid.
- Do not grant the agent access to simulator source or hidden evaluation data.
- Agent may propose tests but cannot weaken guards.

### Controller-generation contract: real code, not a disguised template

Model output contains an actual Python function (or a narrow, code-generating controller DSL if sandbox execution is unavailable):

```python
# Muse-generated file; this is the required function interface.
def control(obs: dict, state: dict) -> tuple[float, dict]:
    """Return pump action [0, 1] and updated serializable state.

    obs = {
      'level': float,       # noisy measurement, normalized 0..1
      'target': float,
      'dt': float,
      'elapsed_s': float,
    }
    state: mutable controller memory encoded as a JSON-compatible dict.
    No file, network, process, GPIO, or wall-clock access.
    """
    ...
```

The **generated policy code must be preserved byte-for-byte** under `artifacts/<run_id>/controller_vN.py`, along with its SHA256, model ID, prompt version, and parent version. Diff v1 against v2. Do not silently patch or rewrite Muse output into a hand-written implementation. Reject invalid code with feedback and allow Muse to revise within the budget.

**Important security boundary:** Static AST linting alone is not a secure Python sandbox. For development, run model-authored Python only inside a constrained disposable container with disabled network, no credentials, read-only root filesystem, non-root user, dropped capabilities, resource/time limits, and no device access. Put the independent evaluator outside that container. If such isolation is unavailable, switch to a **strict declarative controller language** with a trusted interpreter; be explicit that this is generated controller *logic*, not arbitrary generated Python execution. **Never execute unrestricted model-authored Python on the Raspberry Pi.**

### Orchestrator pseudo-code

```python
async def discover_and_control(agent, plant, safety, evaluator):
    session = create_session(goal, constraints, plant.public_capabilities())
    for exp_idx in range(MAX_EXPERIMENTS):
        proposal = await agent.propose_next_experiment(session.public_history())
        approved = safety.validate(proposal, plant.observe())
        result = plant.run(approved) if approved.ok else rejected_result(approved)
        session.record(proposal, result)
        if await agent.ready_to_generate(session.public_history()):
            break

    parent_id = None
    for attempt in range(MAX_CONTROLLER_CANDIDATES):
        candidate_source = await agent.generate_or_revise_controller(
            session.visible_history(), session.last_evaluation(), parent_id
        )
        candidate = registry.persist_immutable(candidate_source, parent_id)
        check = isolated_validator.check(candidate)
        report = evaluator.run(candidate) if check.passed else failed_report(check)
        session.record_candidate(candidate, check, report)
        if report.meets_release_gate:
            return release_candidate(candidate, report)
        parent_id = candidate.id

    return fail_safe_report(session)
```

This pseudo-code must become real code with *finite* budgets, explicit exception handling, idempotent run IDs, and resumable persisted state.

### Required long-running monitoring and repair continuation

**Do not stop the orchestrator when v1 passes its initial test.** The first release enters a monitored control episode. It must accept a hidden disturbance, identify that observed performance diverges from the expected target, and automatically re-enter Muse's revision loop. Model calls occur *between* bounded rollout segments, not at every control tick.

```python
async def monitor_and_repair(selected_v1, plant, agent, evaluator, session):
    # Run the trusted local controller independently of cloud latency.
    baseline_trace = run_bounded_rollout(selected_v1, plant, safety_supervisor)
    session.record_trace(baseline_trace)

    # Operator triggers an undisclosed change on the simulator side.
    await wait_for_disturbance_trigger(session)  # UI action or scripted benchmark
    changed_trace = run_bounded_rollout(selected_v1, plant, safety_supervisor)
    session.record_trace(changed_trace)

    if performance_degraded(changed_trace, baseline_trace):
        session.transition("ADAPTING")
        # Agent receives traces and performance, NOT disturbance parameters.
        v2_source = await agent.revise_controller(
            previous_source=registry.source(selected_v1),
            measured_evidence=session.agent_visible_evidence(),
        )
        v2 = registry.persist_immutable(v2_source, parent=selected_v1)
        report = evaluator.validate_and_compare(
            candidate=v2,
            frozen_baseline=selected_v1,
            same_hidden_seeds=True,
        )
        session.record_candidate(v2, report)
        if report.meets_adaptation_gate:
            session.transition("DEPLOYABLE")
            return v2
        session.transition("FAILED")
        return selected_v1  # Preserve last safe approved controller.
    return selected_v1
```

The actual implementation should support bounded retries if v2 fails, but must *never* auto-promote a worse or unsafe candidate. On a real Raspberry Pi, controller promotion is a distinct explicit user approval after physical-specific validation; a simulator promotion is not hardware authorization.

### How to prove Muse—not predefined automation—actually did the work

- Show raw Muse-generated source for at least **two versions** and a semantic diff.
- Show distinct Muse-proposed experiments tied to specific uncertainties.
- Show it received no true hidden parameters or private test seeds.
- Include an **ablated run** using the same experiment budget but no model-led revision (v1 frozen) to measure adaptation value.
- Compare to a fixed baseline controller; report when Muse does not beat it.
- Preserve model prompts and outputs (with keys/secrets redacted) for audit.

---

## 6. Meta Muse integration: verified endpoints and pragmatic choices

### Model selection

- **Primary:** `muse-wonder-1.0` via Meta Model API for long-horizon hypothesis, experiment planning, code authoring, and revision.
- **Fallback/cheaper option:** `muse-spark-1.3` via the same API, for individual structured tasks or the entire loop if Wonder availability/cost becomes a blocker.
- **Not required for MVP:** SAM 3.1, Muse Image, Muse Voice, Muse Glimmer. These do not solve the primary control-discovery question and would consume time.

Meta documents API base `https://api.meta.ai/v1`, `MODEL_API_KEY`, standard OpenAI-compatible SDK usage, model IDs above, and a Responses API suitable for multi-step agentic work. The exact JSON schema / tool-call format must follow the current docs, not an invented protocol.

**Verified documentation:**

- https://dev.meta.ai/docs/overview
- https://dev.meta.ai/docs/models
- https://dev.meta.ai/docs/protocols
- https://dev.meta.ai/docs/cookbook/structured-output
- https://dev.meta.ai/docs/cookbook/tool-function-calling
- https://dev.meta.ai/docs/api-reference

### Connectivity smoke test (implement as `scripts/check_meta.py`)

```python
import os
from openai import OpenAI

client = OpenAI(
    base_url="https://api.meta.ai/v1",
    api_key=os.environ["MODEL_API_KEY"],
)
reply = client.chat.completions.create(
    model=os.getenv("MUSE_MODEL", "muse-wonder-1.0"),
    messages=[{"role": "user", "content": "Reply exactly: ready"}],
)
print(reply.choices[0].message.content)
```

Use the **Responses API** for the final multi-step tool loop when available; Meta recommends it for reasoning continuity. A temporary Chat Completions adapter is acceptable for fast initial integration if it supplies the *complete externally visible* experiment history on each turn. Implement structured command validation with Pydantic regardless of output mode. Do not assume a model answer is valid just because it parses as JSON.

### Required environment variables

```dotenv
MODEL_API_KEY=                              # never commit
META_BASE_URL=https://api.meta.ai/v1
MUSE_MODEL=muse-wonder-1.0                 # fallback muse-spark-1.3
WORLDPATCH_MODE=sim                        # sim | pi
WORLDPATCH_AGENT_MODE=live                 # live | replay | mock
MAX_MODEL_CALLS_PER_RUN=40
MAX_EXPERIMENTS_PER_RUN=12
MAX_CONTROLLER_CANDIDATES=5
MODEL_TIMEOUT_SECONDS=90
```

Implement exponential backoff for rate limits, bounded retries, and token/cost tracking. `mock` is for CI only. A passing live demo must use actual Muse API calls and expose the model ID.

---

## 7. Implementation modules and repository layout

**Prefer one Python service and one lightweight frontend.** Do not build Kubernetes, Kafka, a database cluster, or an elaborate microservice architecture for a one-week hackathon.

```text
worldpatch/
├── README.md
├── AGENTS.md                        # concise Codex rules derived from this plan
├── pyproject.toml                   # fastapi, uvicorn, pydantic, numpy, scipy, openai, pytest
├── .env.example
├── .gitignore
├── backend/
│   ├── main.py                      # REST + websocket/SSE events
│   ├── schemas.py                   # typed observations, proposals, candidates, scores
│   ├── config.py
│   ├── agent/
│   │   ├── muse_client.py           # provider adapter; model/version logging
│   │   ├── prompts.py               # exact discovery/controller/revision instructions
│   │   ├── orchestrator.py          # finite-state bounded loop
│   │   └── tools.py                 # allowlisted API only
│   ├── plant/
│   │   ├── base.py                  # PlantAdapter abstract class
│   │   ├── tank_sim.py              # hidden plant dynamics
│   │   └── pi_tank.py               # OPTIONAL hardware adapter
│   ├── controller/
│   │   ├── registry.py              # immutable generated versions, hashes, diffs
│   │   ├── validator.py             # structure, static checks, interface
│   │   ├── sandbox.py               # isolated candidate execution
│   │   └── runtime.py               # bounded deterministic local control loop
│   ├── evaluation/
│   │   ├── suite.py                 # seed separation, episodes, disturbance cases
│   │   ├── metrics.py               # MAE, in-band, energy, safety, recovery
│   │   └── baselines.py             # fixed PID and simple on/off policy
│   └── storage/
│       └── sessions.py              # SQLite events + JSONL artifact logs
├── frontend/
│   └── ...                          # React/Vite or Next.js
├── scripts/
│   ├── check_meta.py
│   ├── run_live_demo.py
│   ├── run_evaluation.py
│   └── export_artifacts.py
├── tests/
│   ├── test_sim_determinism.py
│   ├── test_plant_boundary.py
│   ├── test_safety_supervisor.py
│   ├── test_generated_code_isolation.py
│   ├── test_controller_interface.py
│   ├── test_evaluation_seeds.py
│   ├── test_agent_state_machine.py
│   ├── test_muse_contract_mock.py
│   └── test_end_to_end_replay.py
├── docs/
│   ├── IMPLEMENTATION_STATUS.md
│   ├── SAFETY_LIMITATIONS.md
│   ├── DEMO_SCRIPT.md
│   └── BENCHMARKS.md
└── artifacts/                     # generated per run; sample artifacts may be committed
    └── <run_id>/
        ├── event_log.jsonl
        ├── experiments.json
        ├── controller_v1.py
        ├── controller_v2.py
        ├── controller_diff.patch
        ├── evaluation.json
        ├── metrics.csv
        ├── rollout.png
        └── report.md
```

### API contract (suggested)

| Method | Route | Purpose |
|---|---|---|
| `POST` | `/api/runs` | Create a run with goal, limits, plant type, and display label |
| `POST` | `/api/runs/{id}/start` | Start bounded discovery loop; idempotent |
| `GET` | `/api/runs/{id}` | Current stage, selected controller, key metrics |
| `GET` | `/api/runs/{id}/events` | Time-stamped experiment and reasoning event stream |
| `GET` | `/api/runs/{id}/controllers` | Model-authored code versions and diffs |
| `GET` | `/api/runs/{id}/metrics` | Seed-level measurements and aggregate evaluation |
| `POST` | `/api/runs/{id}/disturbance` | Trigger a simulated *hidden* plant change and adaptation |
| `POST` | `/api/runs/{id}/stop` | Stop active run and force neutral actuator output |
| `GET` | `/health` | Service and configured-provider status |

The `/disturbance` endpoint must not tell the agent the exact disturbance mechanism; only the operator UI and hidden evaluator know what changed. Return structured measurements and agent-visible error traces to the model.

### Database model (small is fine)

`Run`, `Experiment`, `Observation`, `ControllerCandidate`, `Evaluation`, `AgentEvent`, and `ModelUsage` with links by `run_id`. Store raw event JSONL as a portable export; SQLite is sufficient for queries.

---

## 8. Controller execution, release gate, and safety

### Candidate validation pipeline

1. **Schema:** Exactly one function conforming to `control(obs, state)` and serializable outputs.
2. **Static checks:** Reject forbidden imports, `eval/exec`, filesystem, network, reflection, subprocesses, and direct hardware access; enforce source size and basic complexity limits. Static checks are defense-in-depth, **not** sufficient security.
3. **Isolated run:** Execute only in a disposable restricted container or a safe interpreted controller DSL.
4. **Interface tests:** Invalid readings, empty state, NaNs, negative `dt`, out-of-range actions, repeated calls, and cold start.
5. **Simulator tests:** Test both exploration-like and held-out plants with deterministic seeds.
6. **Safety checks:** Invalid command ⇒ reject candidate. Any hard safety breach ⇒ stop episode, mark unsafe, never approve.
7. **Compare:** Compute metrics against baseline and v1; only promote if release conditions pass.
8. **Version:** Record SHA, diff, prompts, evaluations, and model source. Rollback must always be possible.

### Trusted local safety supervisor

The supervisor owns the final actuator signal `u_applied`, even if a generated controller requests an invalid value:

```text
if sensor_invalid or stale or emergency_stop or high_level >= hard_cutoff:
    u_applied = 0.0
else:
    u_applied = clamp(controller_u, 0.0, 1.0)
log requested vs applied action, clamp/reject reason
```

**A forced safe stop doesn't count as the controller obeying constraints**: track overrides and score the candidate accordingly. This prevents unsafe controllers from appearing successful merely because the guard blocked their bad actions.

For Raspberry Pi: use a separate low-voltage interlock/float switch or watchdog capable of shutting off the pump independently of model-generated software. Avoid any mains wiring or hazardous autonomous actuation in the hackathon.

---

## 9. Objective success/failure criteria and benchmarks

These are **proposed engineering acceptance criteria**, not claims about achieved results or guarantees that Muse will beat classical control.

### Gate 0 — Basic functionality

**PASS:** Meta connectivity works with a real key; seeded simulator is deterministic; local baseline controls the plant; dashboard charts and logs correspond to real stored events; unit/integration tests pass.  
**FAIL:** API doesn't work, simulation is non-reproducible, logs don't correspond to behavior, or generated-controller isolation is absent.

### Gate 1 — Authentic Muse-led discovery

**PASS:** In a live run, Muse proposes at least **3 distinct bounded experiments**, receives their measured results, records hypotheses and revisions, and authors at least **1 syntactically valid controller** whose source is saved verbatim.  
**FAIL:** Pre-scripted experiments, revealing hidden plant parameters, hand-authoring the final controller while presenting it as Muse output, or only generating text explanations.

### Gate 2 — Generated controller performance

**PASS:** For at least **8 of 10 predefined held-out simulator episodes**, the approved candidate produces valid finite commands, has **zero hard-level violations and zero unauthorized actions**, and reaches **≥70% time-in-band after a reasonable settling period**. Metrics and exact settling window must be frozen in config before evaluation.  
**FAIL:** Hidden-test violations, invalid commands, performance measured only on exploration data, or selective omission of failing episodes.

**Stretch:** Beat a fixed, transparently configured PID baseline by **≥15% median tracking MAE** over predefined held-out episodes *without* higher safety violations or unacceptable energy costs. PID could be excellent; do not misrepresent failure to outperform PID as failure of AI generally. A weaker fixed on/off controller is a useful additional baseline but insufficient by itself.

### Gate 3 — Self-repair after a disturbance (most important judge moment)

**PASS:** With `controller_v1` frozen, induce an undisclosed drainage or pump-efficiency change. Muse sees only measurements and evaluation traces, then authors an auditable **`controller_v2` with a meaningful logic/code change**. In at least **3 of 5 predefined disturbance tests**, v2 reduces the post-disturbance MAE by **≥20% relative to frozen v1**, with **zero hard safety violations**.  
**FAIL:** v2 is only a renamed copy, a hidden automatic retune performed outside Muse, or improvement exists only on cherry-picked disturbances.

**Important:** The benchmarks are ambitious within a few days. If the system fails a gate, present the measured failure and scope the final demo to the strongest *actually working* capability. Never falsify results.

### Gate 4 — Raspberry Pi (optional)

**PASS:** Same `PlantAdapter` API controls a 5–12 V small pump with independent interlock; telemetry reflects physical measurements; an approved controller maintains level within an agreed range for a short bounded test; pump turns off on loss of network, sensor faults, emergency stop, and host shutdown.  
**FAIL:** Controller bypasses an interlock, unsafe power/water setup, unverifiable sensor readings, or requiring a cloud response to stop the pump.

### Ablation study / comparative evaluation

Run and compare these predetermined cases:

| Variant | Learns via experiments | Writes controller | Revises after failure |
|---|---|---|---|
| Fixed baseline PID | No | No | No |
| Fixed baseline on/off | No | No | No |
| Muse v1 frozen | Yes | Yes | No |
| Full WorldPatch | Yes | Yes | Yes |

Record source versions, MAE, in-band %, energy, override count, safety violations, recovery duration, model calls, and total run duration. Add confidence intervals only if enough independent runs exist; otherwise show raw seeds and distributions.

---

## 10. Frontend design: only the elements that strengthen the proof

Single desktop-friendly page with four functional sections:

1. **Plant:** Animated tank or line chart; target band, measured level, commanded/applied pump power, disturbance marker.
2. **Agent timeline:** "Hypothesis → Experiment → Observation → Controller v1 → Test → Failure → v2" with actual time stamps, tool arguments and outcomes.
3. **Controller code:** Diff viewer for v1/v2 and metadata (model, hash, validation status); never display a template masquerading as generated code.
4. **Evidence:** Side-by-side plots for v1 and v2 on the *same held-out disturbance*, numerical scores, baseline line, pass/fail gates and model usage.

**Controls:** `Start Discovery`, `Introduce Disturbance`, `Compare v1/v2`, `Stop`, `Export Evidence`, and optional `Switch Simulation / Raspberry Pi`. All controls must be wired to real backend actions. Disabled controls must honestly explain prerequisites.

Suggested graph: water level vs seconds (target band shaded) with overlay of pump action, and a vertical marker when the disturbance starts. Show real result labels: `Simulated system` or `Physical hardware`.

### Three-minute demo script

- **0:00–0:20 — Hook:** "This machine has no operating manual, dynamics model, or controller. WorldPatch will learn it from observations and write control code."
- **0:20–0:55 — Discovery:** Show real Muse experiment proposals, the tank responding, and the learning trace.
- **0:55–1:25 — Creation:** Open `controller_v1.py`, demonstrate it running and charting control error.
- **1:25–2:05 — Change:** Press `Introduce Disturbance`; v1 degrades. Show Muse reading failure evidence and generating an actually different `controller_v2.py`.
- **2:05–2:40 — Proof:** Run v1 and v2 against identical hidden scenarios; display real before/after metrics and safety checks, including baseline.
- **2:40–3:00 — Significance:** Explain the reusable control protocol and future Raspberry Pi / real-world deployment; explicitly state that real-world safety isn't established by simulation.

Use a recorded real session if cloud latency would make live stage timing unreliable; the original run logs must match what is shown. Be explicit about accelerated simulation and prerecorded sections.

---

## 11. Implementation schedule (priority-driven)

**Oct 30 — Build foundation:** Set up repository, simulator, contracts, baseline controllers, metrics, deterministic seeds, API connectivity. Execute and commit unit tests.  
**Oct 31 — Real agent loop:** Muse experiment proposals + limited tools + state machine + logs; store generated source; implement sandbox validation.  
**Nov 1 — Discovery and controller v1:** End-to-end real Muse run, consistent candidate evaluation, minimal working dashboard, first evidence artifact.  
**Nov 2 — Adaptation and benchmark:** Hidden disturbance, Muse-generated v2, comparisons against v1 and baselines, test 10+ seeds, fix correctness issues.  
**Nov 3 — Reliability and demo:** UI, controlled replay, run export, README, architecture diagram, public repo, video recording. **Only if everything above passes, connect Raspberry Pi.**  
**Nov 4 — Submission:** Confirm original hackathon work, clean public source, remove secrets, three-minute video, submitted before 9 PM ET. Allow time for upload and unexpected failures.

### Stop/go checkpoints

- **Checkpoint A (Oct 31):** Real Muse returns valid structured experiment proposals. If not, use Spark fallback, simplify schema, and fix connectivity before advancing.
- **Checkpoint B (Nov 1):** Real Muse has authored a source artifact; at least one controller runs safely in independent evaluation. If not, freeze UI work and focus on the generation/validation loop.
- **Checkpoint C (Nov 2):** At least one disturbance causes v1 degradation and an identifiable v2 revision. If v2 performs worse, keep truthful results and tune experimental protocol; do not fake a recovery.
- **Checkpoint D (Nov 3):** Reproducible artifacts and short demo work on a clean machine. Only then build hardware or a second plant.

### P0 / P1 / P2 cut line

**P0 indispensable:** simulator, Muse-led tool loop, generated code, isolation, v1/v2, deterministic evaluator, minimal graphs, export, tests.  
**P1 valuable:** Raspberry Pi adapter, independent interlock, physical experiment, polished diff UI.  
**P2 optional:** second plant, richer self-identification reports, SAM/vision integration, voice UI, automatic experiment design optimization, distributed hardware fleet.

---

## 12. Raspberry Pi extension: minimal hardware implementation

### Hardware suggestion (not yet purchased or tested)

- Raspberry Pi 4/5, power supply, microSD/SSD.
- Low-voltage 5–12 V submersible DC pump with appropriate driver/MOSFET module and separate pump supply.
- Water reservoir plus transparent container; return tube or controlled drain; spill tray.
- Continuous level sensor appropriate for water (e.g. calibrated pressure or time-of-flight sensor) plus **independent high-level float cutoff**.
- Optional water-safe power isolation, external emergency-stop switch, leak detection, waterproof connectors.

**Never** power the pump from a GPIO pin, switch mains equipment, place exposed electronics near water, bypass the interlock, or trust an LLM to enforce safety limits. Test in a protected area with a small volume of water and adult supervision.

### Hardware adaptation

```python
class PlantAdapter(Protocol):
    def observe(self) -> dict: ...
    def apply_input(self, u: float, duration_s: float) -> dict: ...
    def reset(self) -> None: ...
    def emergency_stop(self) -> None: ...
```

`TankSimulator` and `PiWaterTank` satisfy this interface. Runtime controller artifacts must be identical across modes **but validated and approved separately** for the physical device. The Pi process enforces local rate limiting, timeout, input clamping, sensor sanity checks, logging, and interlock state. Real-time low-level actions must not depend on Meta API responsiveness.

### Pi MVP acceptance evidence

Video of actual small tank; timestamped telemetry; unplug network while the approved controller continues or enters safe local fallback; trigger high-level float or simulated sensor-loss condition and verify independent pump cutoff; show manual emergency stop. Never claim field-proven industrial reliability.

---

## 13. Real test checklist for Codex

### Unit tests

- [ ] With fixed seed, simulator traces are bit-for-bit or tolerance-reproducible.
- [ ] `u < 0`, `u > 1`, NaN/Inf, negative duration, missing readings are rejected.
- [ ] High-level supervisor overrides actions and records violations.
- [ ] Agent cannot request arbitrary commands or access hidden parameters via tools.
- [ ] Controller state round-trips through JSON serialization.
- [ ] All generated-controller execution is isolated (or uses the restricted DSL).
- [ ] Candidate cannot read filesystem/secrets, access network, or manipulate host process.
- [ ] Every run records immutable source hash, parent ID and evaluation results.

### Integration tests

- [ ] Simulated `fake_muse` output exercises the complete workflow in CI without spending credits; flagged clearly as fake.
- [ ] Real Muse API smoke test works and is marked `live`.
- [ ] 3 bounded experiments produce valid observed telemetry.
- [ ] A real model produces code saved under `controller_v1.py`.
- [ ] Bad code produces useful validation feedback and retry, not silent patching.
- [ ] Known disturbance causes measurable deviation from frozen v1.
- [ ] v2 evaluation occurs on the same held-out disturbance conditions as v1.
- [ ] Network failure stops further experiments but does not disable local safety controls.

### Demo / release checklist

- [ ] Public GitHub repository, clear license and provenance, `.env` excluded.
- [ ] `README.md` includes setup and one command to run evaluation/replay.
- [ ] `docs/BENCHMARKS.md` contains real seed-level scores (including failures).
- [ ] Actual Meta model, calls, usage, and resulting code are visible.
- [ ] Screen recordings match actual artifacts; no fabricated live outputs.
- [ ] Original hackathon contributions are identified clearly.
- [ ] Three-minute demo video has accessible link and clear narration.
- [ ] Safety limitations plainly stated; no universal control or production-grade claim.

---

## 14. The first commands Codex should execute

```bash
mkdir -p worldpatch && cd worldpatch
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install fastapi uvicorn pydantic numpy scipy pandas matplotlib openai pytest httpx
# Implement a local simulator first, then run:
pytest -q
# Configure MODEL_API_KEY in .env or environment and then:
python scripts/check_meta.py
# After backend/UI exist:
uvicorn backend.main:app --reload
```

Do not assume that `scripts/check_meta.py` exists until you create it. The suggested frontend can use Vite + React and `recharts` or simple SVG plots; choose the faster route and document the commands in README. Use `git status` and small commits after each verified milestone.

---

## 15. Prompts/behavioral contracts for the runtime Muse agent

### Discovery agent system contract

> You are an experimental control engineer working with an **unknown physical system**. You may only interact through the provided safe tools. Your goal is to identify how the system responds to controls, using as few bounded experiments as possible, and then author a control policy that meets the target constraints. Explicitly state your current hypothesis, the uncertainty your next experiment reduces, and why the experiment is safe. Never claim access to the true model, hidden parameters, or hidden future scenarios. Never request exceptions to hard safety limits. If the data is insufficient, ask for another bounded experiment rather than inventing physics.

### Controller authoring contract

> Given the documented `control(obs, state)` interface, sensor measurements, prior experiments and candidate evaluations, write a **complete new control function**. No imports, hardware access, arbitrary files, environment variables, network, process execution, or non-deterministic dependencies. Return complete code plus concise explanation and test expectations. Your policy must produce bounded finite actions and maintain JSON-serializable state. Prioritize robustness to lag and disturbances. You may implement established control logic if justified by observed evidence, but do not copy a pre-provided fixed controller. Never state success before the evaluator runs.

### Repair contract

> The deployed controller failed or degraded in the following **measured** ways. Analyze observations; propose at least one plausible causal explanation; produce a meaningful code modification targeted to those failures; predict how its behavior should change; and submit the revised complete source. The independent evaluator—not your explanation—will determine if the repair succeeded. Stay within hard safety limits.

Store each prompt version in `backend/agent/prompts.py` and save the prompt hash with the generated artifact.

---

## 16. Evidence and positioning for judges

### Proposed title and description

**WorldPatch — A self-discovering control engineer for physical machines.**

"Meta Muse learns a machine's dynamics from bounded experiments, writes an executable controller, verifies it in a sandbox, and repairs it when the machine's behavior changes. A reusable interface could one day help retrofit simple equipment with adaptive, observable control."

### A precise innovation claim

**We built an agentic control-engineering pipeline** connecting hypothesis formation, active experimentation, model-authored code, independent safety validation, and self-repair. We demonstrate that pipeline on held-out black-box simulations. This is a new project implementation—not a claim that autonomous control or machine learning for control has never existed.

### What not to claim

- "Works on any machine" — unproven; different machines may need different sensing, control structures, and validation.
- "Zero accidents / guaranteed safety" — false from simulation-only testing.
- "Muse learned physical laws from scratch" — too strong; it observed an engineered simulator and may leverage prior training.
- "AI outperforms PID" — only say so with same-seed measured data and appropriate baselines.
- "Raspberry Pi deployed" — only if genuinely completed and tested.

### Success story in one sentence

> "We handed Muse an unknown machine, allowed it only safe experiments, watched it write a working controller, changed the machine, and watched Muse repair its own code—with the measurements and source diffs to prove each step."

---

## 17. References and official resources

**Hackathon:** https://events.cerebralvalley.ai/e/meta-ai-developer-hackathon  
**Meta Model API overview:** https://dev.meta.ai/docs/overview  
**Model listing:** https://dev.meta.ai/docs/models  
**Responses vs Chat API:** https://dev.meta.ai/docs/protocols  
**Structured output cookbook:** https://dev.meta.ai/docs/cookbook/structured-output  
**Tool/function calling cookbook:** https://dev.meta.ai/docs/cookbook/tool-function-calling  
**Meta API reference:** https://dev.meta.ai/docs/api-reference

Use the participant guide's exact submission rules: new work during hackathon, public repo, legitimate assets, max four team members, and three-minute demo video. Confirm any updated policies in the event dashboard/Discord.

---

## 18. Paste this into Codex to start the build

```text
Read WORLDPATCH_CODEX_IMPLEMENTATION_PLAN.md in full and implement WorldPatch.
Prioritize P0: deterministic unknown water-tank simulator, Meta Muse agent with
bounded experiment tools, model-authored controller.py generation, isolated
validation, independent held-out testing, disturbance-triggered code revision,
and visible evidence dashboard. Do not write a fake agent, hard-code the model's
controller, or claim test success without running it. Create AGENTS.md, follow
all safety restrictions, implement files in the proposed repository layout,
and keep docs/IMPLEMENTATION_STATUS.md updated with progress and blockers.
First achieve a complete working discovery -> v1 -> disturbance -> v2 loop;
then benchmark and polish. If MODEL_API_KEY is missing, use an explicitly
labeled mock only for CI and show the exact live verification commands. Skip
Raspberry Pi until simulation passes. Keep all work ready for a public repo.
```

---

## 19. Final instruction for Codex

**Start with the physical simulator and actual model connection.** Build the smallest complete loop first: `Muse plans experiment → simulator measures response → Muse generates controller.py → independent evaluator tests → Muse revises → evaluator retests`. Once this works and is quantitatively reproducible, add the polished dashboard and optional Pi.

**Do not stop after scaffolding, wireframes, or mocked calls.** Run the unit tests, perform at least one real Meta model-assisted experiment and controller generation when credentials are present, and show actual evaluation data. If credentials, Docker, or hardware are unavailable, implement everything else, clearly mark the blocked live steps, and provide precise commands to complete verification. Favor a truthful working MVP over a larger incomplete promise.
