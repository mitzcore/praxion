# Praxion — submission text (2026-11-04; numbers from docs/HARDWARE_RESULTS.md and docs/BENCHMARKS.md)

## One-liner (≤ 140 chars)
An AI control engineer that learns an unfamiliar machine, writes its own controller, and repairs it when the machine changes. Proven on hardware.

## Short description (≤ 600 chars)
Praxion hands a Meta Muse model a machine it has never seen. Muse designs bounded experiments, writes a controller in Python, and that code is scored on hidden scenarios in a sealed sandbox before deployment. When the machine changes, a trusted monitor fires, Muse re-identifies the machine, diagnoses it and writes a repaired controller, promoted only if it beats the frozen original. On a $50 heater board, four of four promoted repairs then beat the original when both ran on the board itself. Failures are kept and reported.

## Long description

**The problem.** Every pump, heater and tank in industry has a controller tuned once by an engineer who first had to learn the machine. Machines drift: a pump wears, a valve sticks, a heater weakens. The controller keeps the old recipe and the process leaves its band. Nobody re-identifies the machine; nobody redesigns the controller.

**What Praxion does.** One loop, done to the bone: discover → author → gate → deploy → detect → diagnose → repair → re-gate.
- Muse (muse-spark-1.3 through the Meta Model API, structured outputs) proposes bounded experiments; a trusted supervisor checks the worst case before anything runs.
- Muse writes `controller_v1.py`. Trusted code static-checks it, runs it in a Docker sandbox (no network, read-only, non-root) and scores it on hidden scenarios whose seeds, parameters and true state the model never sees.
- A trusted monitor watches the deployed controller. When it fires, Muse runs new experiments on the changed machine, names a diagnosis and writes `controller_v2.py`, promoted only if it cuts post-change error ≥ 20 % on ≥ 3 hidden scenarios with zero safety violations.
- The model is blind by construction (`tests/test_agent_blindness.py` scans every stored prompt); every artifact is hashed, and an independent audit script reconstructs each run from its bundle.

**What happened (simulation).** Run v13-s11: 12 experiments, v1 passed 10/10 hidden scenarios, a hidden 24 s transport delay was added, the monitor fired at 89 s, Muse measured the delay from its own experiments and detuned for it: post-change error fell 90.6 % on the same frozen scenarios. Across five hidden machines protocol 1.3 repaired 5/5 (in-sample; disclosed). A 1984 relay auto-tuner beats our repairs on post-change error in 11 of 12 runs; we report it.

**What happened (hardware).** Ten runs on an APMonitor TCLab heater board; nothing changed but the plant driver. First controller passed 7/10. The monitor caught the change 8/8 times (66–153 s). Diagnosis correct 7/7. The gate promoted a repair in 4 of 7 attempts. Then the part that matters: for each promoted repair, the frozen original and the repair ran **on the physical board** under the same fault, with a forecast from the fitted twin stored before each trial. **The repair won 4 of 4** (post-change error cut 58 %, 75 %, 66 %, 34 %; one-sided sign test p = 0.0625; 95 % interval 0.40–1.00), with zero safety interventions in 11 board trials. One fault was a room fan switched on by hand and filmed; the other three were a trusted 55 % derate of the heater command, run unattended overnight. The three attempts that produced no acceptable repair, the run where the fault was too small to beat, and the run that lost to API timeouts are all in `docs/HARDWARE_RESULTS.md`, generated from the bundles.

**Honesty.** No fabricated evidence; failed gates are reported; the first hardware run failed and is kept; every promoted repair overshoots on warm-up (reported, not gated); the twin's forecast under-rates aggressive repairs, so the board measurement is the claim; no PID baseline on the board yet; one plant type in simulation, one on hardware; no "any machine", no "guaranteed safe".

**Stack.** Python 3.12, FastAPI, numpy/scipy, OpenAI SDK against the Meta Model API (structured outputs), Docker sandbox, React dashboard, pytest (645 tests). Meta Muse authors every experiment plan, controller and repair; trusted code never edits them.

## Links
- Repo: https://github.com/mitzcore/praxion
- Video: [link]
- Evidence: `docs/HARDWARE_RESULTS.md`, `docs/BENCHMARKS.md`, `docs/AUDIT_2026-11-02.md`, `artifacts/runs/*`
