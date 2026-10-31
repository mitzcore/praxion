# Praxion demo script

A screen recording of the real dashboard replaying recorded run `v13-s11-20261031-020922-a0e68e` (muse-spark-1.3, plant seed 11, protocol v1.3), plus one terminal shot of the audit. Every value on screen is read from the stored bundle. Nothing is recomputed or staged.

## How the footage is made

```bash
cd frontend && npm install && npm run build && cd ..
uv run python scripts/record_demo.py --run v13-s11-20261031-020922-a0e68e   # --speed-a 4 --speed-b 16 are the defaults
```

`scripts/record_demo.py` drives the dashboard in headless Chromium and writes `artifacts/demo/v13-s11-20261031-020922-a0e68e/`: `demo.webm`, one screenshot per segment, `audit.txt`, `audit.png`, and `segments.json` with the offsets used below. `artifacts/demo/` is gitignored. The video is attached to the submission separately.

The recording has two passes:
- **Pass A, 4×** (raw 0.00 to 85.92 s): intro and discovery.
- **Pass B, 16×** (raw 85.92 to 131.79 s): authoring, gate, monitor, repair. Pass B starts with a replay restart that repeats discovery (raw 85.92 to 106.11 s). **Cut that stretch in editing.**
- **Close-ups** (raw 131.79 to 175.48 s): held views of the final state, then the audit terminal.

Raw `demo.webm` length is 175.44 s. After the 20.19 s cut, the edited video is about 2:35.

Edit order: keep raw order, except place the audit shot (raw 168.79 to 175.48) before the closing header (raw 163.52 to 168.79). Then the honesty statement comes last.

Keep the REPLAY badge (speed, run id, recording time) visible in every dashboard shot.

## Script

Edited times are after the cut and the audit swap. Raw offsets are seconds into `demo.webm` from `segments.json`.

| Edited time | Raw offset (s) | Pass | On screen | Spoken line |
|---|---|---|---|---|
| 0:00 to 0:15 | 0.00 to 15.0 | A, 4× | Header: "REPLAY 4x · v13-s11-20261031-020922-a0e68e", LIVE MUSE, protocol v1.3, docker sandbox, muse-spark-1.3. Plant panel starts empty, then E1. | "This is a recorded run of Praxion. A Meta Muse model gets a simulated water tank it has never seen. No parameters, no controller. It has to hold the level at 0.6 without overflowing." |
| 0:15 to 0:50 | 15.0 to 50.0 | A, 4× | Timeline: E1 to E4 with stated uncertainty and safety argument. Hypothesis ledger revisions. Plant panel: measured level under each constant pump command. | "Muse proposes one bounded experiment at a time. Each says which uncertainty it targets and why it is safe. The supervisor checks a worst-case bound before anything runs. After each result, Muse revises its hypotheses. It sees only noisy measurements, never the true parameters." |
| 0:50 to 1:20 | 50.0 to 80.45 | A, 4× | E5 to E12: shorter holds near the target, ledger revisions continuing (12 experiments, 12 ledger revisions). | "The later experiments probe the operating point near 0.6. The pump duty that holds the level there is the main unknown." |
| 1:20 to 1:26 | 80.45 to 85.92 | A, 4× | Timeline: "experiment budget exhausted". | "Muse did not declare itself ready. The 12-experiment budget ran out, so the orchestrator moved on to authoring." |
| (cut) | 85.92 to 106.11 | B | replay restart repeating discovery | (removed in editing) |
| 1:26 to 1:52 | 106.11 to 131.79 | B, 16× | Live pass at 16×: v1 registered, held-out evaluation, disturbance marker, monitor fires, after-change experiments E13 to E16, v2 registered, final stage COMPLETE. | "At sixteen times speed: Muse writes a controller, it is scored on hidden scenarios and deployed. Then we change the machine. A monitor detects it, Muse runs experiments on the changed machine, and writes a repair." |
| 1:52 to 2:02 | 131.79 to 141.81 | close-up | Code panel: `controller_v1.py`, sha256 686ea165e103e5ae "verified", 2326 bytes, prompt hash 0d19650e641cac11, static / sandbox pass / pass. Held-out table: v1 10/10, median MAE 0.0132, in-band 92.5%; fixed PID 0.0080, 100.0%. | "Muse wrote this controller. It is stored byte for byte and ran in a sandbox with no network. It passed 10 of 10 hidden scenarios. The fixed PID baseline tracked better here." |
| 2:02 to 2:11 | 141.81 to 150.87 | close-up | Plant panel with disturbance marker. Trusted monitor: degraded at t = 89.5 s, baseline window MAE 0.0124, threshold 0.0500, recent window MAE 0.2635. | "We added a transport delay to the pump. Muse was not told. A trusted monitor, not the model, flagged the degradation at 89.5 seconds." |
| 2:11 to 2:19 | 150.87 to 158.76 | close-up | Code panel: v1 to v2 diff (+91 −52). Muse diagnosis (`response_slower`): "Same u now acts ~24 s later …". | "From its own experiments on the changed machine, Muse measured the new delay at about 24 seconds, and detuned the controller for it." |
| 2:19 to 2:23 | 158.76 to 163.52 | close-up | Repair v2 vs frozen v1: G3 PASS, 5/5 improved, median reduction 90.6%, diagnosis matched the injected family, nominal after repair PASS, recorded COMPLETE. | "On the same frozen scenarios, error after the change fell 90.6 percent, with zero violations." |
| 2:23 to 2:30 | 168.79 to 175.48 | terminal | `audit_run.py` output: check 6 lines "v1 == call #12 … 2326 B", "v2 == call #17 … 3650 B", and `RESULT: PASS (7 pass, 0 warn, 0 fail)`. | "Anyone can audit the bundle. Every controller is byte-identical to what Muse returned. No view leaked hidden data." |
| 2:30 to 2:35 | 163.52 to 168.79 | close-up | Header: "REPLAY 16x · v13-s11-20261031-020922-a0e68e". | See closing below. Hold the frame, or the final frame, until the line ends. |

## Closing (spoken over the last shot; hold the frame as needed)

"This is our best run, not our typical one. Across five hidden machines, protocol v1.3 repaired all five, but only three kept working on the original machine. Our first full run failed to repair, and we kept that result. We used Spark, and tried Wonder only once. This is simulation only. Nothing here shows it works on real hardware."

The closing runs about 15 s over a held frame, which brings the edited video to about 2:50.

## Rules for the recording

- Use only recorded runs. Do not trim the replay to hide a failure.
- Do not say: works on any machine, guaranteed safe, beats PID, deployed on hardware, Muse learned physics.
- Every number spoken must appear on screen in that shot, or come from the sources below.

## Numbers used, with sources

| Number | Source |
|---|---|
| all raw offsets, 175.44 s video, 20.19 s cut (85.92 to 106.11) | `artifacts/demo/v13-s11-20261031-020922-a0e68e/segments.json` |
| 12 experiments, budget exhausted, 12 ledger revisions | `segments.json` observed values; `artifacts/runs/v13-s11-20261031-020922-a0e68e/event_log.jsonl` |
| v1 2326 bytes, sha256 686ea165e103e5ae | `artifacts/runs/v13-s11-20261031-020922-a0e68e/controller_v1.meta.json` |
| v1 10/10, MAE 0.0132, in-band 92.5%; PID 0.0080, 100.0% | `artifacts/runs/v13-s11-20261031-020922-a0e68e/evaluation_v1.json` |
| degraded at 89.5 s, 0.0124, 0.0500, 0.2635 | `artifacts/runs/v13-s11-20261031-020922-a0e68e/monitoring.json` |
| delay about 24 s, `response_slower` | `artifacts/runs/v13-s11-20261031-020922-a0e68e/controller_v2.meta.json` |
| diff +91 −52 | `segments.json` observed values (dashboard diff header) |
| 5/5 improved, 90.6%, zero violations, nominal after repair PASS | `artifacts/runs/v13-s11-20261031-020922-a0e68e/adaptation_v2.json`, `evaluation_disturbance_v2.json` |
| audit 7 pass, call #12 and #17 | `artifacts/demo/v13-s11-20261031-020922-a0e68e/audit.txt`; `scripts/audit_run.py` |
| five machines repaired, three kept nominal | `docs/IMPLEMENTATION_STATUS.md` (protocol v1.3 batch) |
| first full run failed repair | run `spark2-20261031-004636-3d012e`, `docs/IMPLEMENTATION_STATUS.md` |
