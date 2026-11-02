"""EXPLORATION diagnostic (not part of the frozen evaluator): what does the classical re-tune's post-change
MAE win cost in robustness?

The relay re-tuned PI lands near kp 0.25, Ti ~180 s, with its bias set to the pre-change mean input: close to an
open-loop bias hold. The frozen disturbance suite applies one change and then nothing else, so a correct bias
plus a very slow loop scores a near-zero MAE. This script asks the question the suite does not: after the
actuator_lag change (60 s), apply a SECOND disturbance at 180 s (pump_derate, extra_leak or drain_shift, seeded
default magnitude) and score 210-420 s. Compared on the same plant seeds, same exploration scenario seeds
(101-105, never the hidden 1000s/2000s):

  relay PI re-tuned (gains exactly as scored in artifacts/benchmarks/latest.json), relay PI nominal,
  the hand-tuned slow PID, the fixed PID, and the Praxion controller promoted in each run (v2, sha-verified,
  run in the Docker sandbox).

Also runs the lag-only condition on the same exploration scenarios so the head-to-head result is replicated
off the hidden seeds. Writes artifacts/benchmarks/second_disturbance_diagnostic.{json,md}.

  uv run python scripts/diagnose_second_disturbance.py [--sandbox docker|subprocess_dev_only] [--scenarios 101 105]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import statistics
import sys
import time
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.controller.runtime import run_episode
from backend.controller.sandbox import docker_available, make_sandbox
from backend.evaluation.baselines import SLOW_PID_TUNING, PIDController
from backend.evaluation.config import BAND, DISTURBANCE_AT_S, TARGET
from backend.evaluation.metrics import compute_metrics
from backend.plant.tank_sim import TankSimulator
from backend.safety.supervisor import Supervisor
from backend.schemas import DisturbanceSpec

ROOT = Path(__file__).resolve().parents[1]
SECOND_AT_S = 180.0
EPISODE_S = 420.0
SCORE_FROM_S = SECOND_AT_S + 30.0
SECOND_FAMILIES = ("pump_derate", "extra_leak", "drain_shift")
RECOVERY_TOL = 0.025
RECOVERY_HOLD_S = 10.0


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _recovery_s(trace, after_s: float) -> float | None:
    """First time after `after_s` at which |y - target| stays within RECOVERY_TOL for RECOVERY_HOLD_S."""
    need = round(RECOVERY_HOLD_S / trace.dt)
    run = 0
    for s in trace.steps:
        if s.t < after_s:
            continue
        run = run + 1 if abs(s.h_true - trace.target) <= RECOVERY_TOL else 0
        if run >= need:
            return round(s.t - (need - 1) * trace.dt - after_s, 1)
    return None


def _episode(ctrl, plant_seed: int, scenario: int, second: str | None) -> dict[str, Any]:
    tr = _run_with_schedule(ctrl, plant_seed, scenario, second)
    m = compute_metrics(tr, SCORE_FROM_S)
    peak = max((abs(s.h_true - TARGET) for s in tr.steps if s.t >= SECOND_AT_S), default=float("nan"))
    return {"mae": m.mae, "in_band": m.in_band_fraction, "hard": m.hard_violations, "overrides": m.override_count,
            "invalid": m.invalid_outputs, "peak_abs_err_after_second": peak, "recovery_s": _recovery_s(tr, SECOND_AT_S)}


def _run_with_schedule(ctrl, plant_seed, scenario, second):
    """run_episode calls plant.reset, which clears scheduled disturbances, so the schedule is re-applied in a
    thin subclass hook. Fresh plant and supervisor per episode, as in the evaluator."""

    class _Plant(TankSimulator):
        def reset(self, seed, scen=None):
            obs = super().reset(seed, scen)
            self.schedule_disturbance(DisturbanceSpec(family="actuator_lag", at_t=DISTURBANCE_AT_S))
            if second:
                self.schedule_disturbance(DisturbanceSpec(family=second, at_t=SECOND_AT_S))
            return obs

    return run_episode(_Plant(), ctrl, Supervisor(), EPISODE_S, TARGET, plant_seed, scenario=scenario)


def _med(xs):
    v = [x for x in xs if x is not None and not math.isnan(x)]
    return statistics.median(v) if v else None


def _fmt(x, nd=4):
    return "—" if x is None or math.isnan(x) else f"{x:.{nd}f}"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sandbox", default="docker", choices=["docker", "subprocess_dev_only"])
    ap.add_argument("--scenarios", type=int, nargs=2, default=(101, 105), metavar=("FIRST", "LAST"))
    ap.add_argument("--out", default="artifacts/benchmarks/second_disturbance_diagnostic")
    args = ap.parse_args()
    for s in range(args.scenarios[0], args.scenarios[1] + 1):
        assert s < 1000, "exploration scenario seeds only; never the hidden 1000s/2000s"
    scenarios = list(range(args.scenarios[0], args.scenarios[1] + 1))
    if args.sandbox == "docker" and not docker_available():
        print("docker not available; pass --sandbox subprocess_dev_only (dev-only, labeled)", file=sys.stderr)
        return 2

    bench = json.loads((ROOT / "artifacts/benchmarks/latest.json").read_text())
    runs = [r for r in bench["runs"] if r.get("disturbance_family") == "actuator_lag" and not r.get("full_equals_v1")
            and (r.get("baseline_tuning") or {}).get("relay_pi_retuned", {}).get("actuator_lag", {}).get("retuned")]
    print(f"{len(runs)} runs with a promoted repair under actuator_lag; scenarios {scenarios}; sandbox {args.sandbox}")

    conditions = [None, *SECOND_FAMILIES]
    results: list[dict[str, Any]] = []
    t0 = time.time()
    for r in runs:
        rid, seed = r["run_id"], int(r["plant_seed"])
        bt = r["baseline_tuning"]
        g_re = bt["relay_pi_retuned"]["actuator_lag"]["gains"]
        g_nom = bt["relay_pi"]["gains"]
        v2_path = ROOT / "artifacts/runs" / rid / "controller_v2.py"
        meta = json.loads((v2_path.with_suffix(".meta.json")).read_text())
        sha = _sha(v2_path)
        assert sha == meta["sha256"], f"{rid}: controller_v2.py sha mismatch"
        trusted = {
            "relay_pi_retuned": PIDController(kp=g_re["kp"], ki=g_re["ki"], kd=g_re["kd"], u_bias=g_re["u_bias"], name="relay_re"),
            "relay_pi_nominal": PIDController(kp=g_nom["kp"], ki=g_nom["ki"], kd=g_nom["kd"], u_bias=g_nom["u_bias"], name="relay_nom"),
            "slow_pid": PIDController(**SLOW_PID_TUNING, name="slow_pid"),
            "fixed_pid": PIDController(name="fixed_pid"),
        }
        prax = make_sandbox(v2_path.read_text(), name=f"{rid}-v2", mode=args.sandbox)
        try:
            for second in conditions:
                for scen in scenarios:
                    row = {"run_id": rid, "plant_seed": seed, "scenario": scen, "second": second or "none", "controllers": {}}
                    for name, c in trusted.items():
                        row["controllers"][name] = _episode(c, seed, scen, second)
                    row["controllers"]["praxion_v2"] = _episode(prax, seed, scen, second)
                    results.append(row)
                print(f"  {rid} seed {seed}: done ({time.time() - t0:.0f} s)", flush=True)
        finally:
            prax.close()

    names = ["praxion_v2", "relay_pi_retuned", "relay_pi_nominal", "slow_pid", "fixed_pid"]
    summary: dict[str, dict[str, dict[str, Any]]] = {}
    for second in conditions:
        key = second or "none"
        rows = [x for x in results if x["second"] == key]
        summary[key] = {}
        for n in names:
            cs = [x["controllers"][n] for x in rows]
            summary[key][n] = {
                "median_mae": _med([c["mae"] for c in cs]), "median_in_band": _med([c["in_band"] for c in cs]),
                "median_peak": _med([c["peak_abs_err_after_second"] for c in cs]),
                "median_recovery_s": _med([c["recovery_s"] for c in cs]),
                "recovered_frac": sum(c["recovery_s"] is not None for c in cs) / len(cs) if cs else None,
                "hard_total": sum(c["hard"] for c in cs), "overrides_total": sum(c["overrides"] for c in cs),
                "invalid_total": sum(c["invalid"] for c in cs), "n": len(cs),
            }
    # per-run wins on the second-disturbance conditions
    wins = {"praxion_v2": 0, "relay_pi_retuned": 0, "n": 0}
    for x in results:
        if x["second"] == "none":
            continue
        a, b = x["controllers"]["praxion_v2"]["mae"], x["controllers"]["relay_pi_retuned"]["mae"]
        wins["n"] += 1
        wins["praxion_v2" if a < b else "relay_pi_retuned"] += 1

    out = {"generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"), "sandbox": args.sandbox, "scenarios": scenarios,
           "episode_s": EPISODE_S, "first": {"family": "actuator_lag", "at_s": DISTURBANCE_AT_S},
           "second_at_s": SECOND_AT_S, "score_from_s": SCORE_FROM_S, "band": list(BAND), "target": TARGET,
           "runs": [r["run_id"] for r in runs], "summary": summary, "episode_wins_second_conditions": wins,
           "episodes": results}
    Path(args.out + ".json").write_text(json.dumps(out, indent=1))

    L = ["# Second-disturbance diagnostic (exploration, not a frozen gate)", "",
         (f"Generated {out['generated_at']}. actuator_lag at {DISTURBANCE_AT_S:.0f} s, second disturbance at {SECOND_AT_S:.0f} s "
         f"(seeded default magnitude), scored {SCORE_FROM_S:.0f}–{EPISODE_S:.0f} s on true level. Exploration scenario seeds "
         f"{scenarios[0]}–{scenarios[-1]} (hidden seeds untouched). Runs: {len(runs)} promoted repairs under actuator_lag, "
         f"Praxion controllers run in the `{args.sandbox}` sandbox. Peak = max |level − target| after the second change; "
         f"recovery = first time |level − target| ≤ {RECOVERY_TOL} held {RECOVERY_HOLD_S:.0f} s."), "",
         "| second disturbance | controller | median MAE | median in-band | median peak | median recovery s | recovered | hard ticks | overrides | episodes |",
         "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|"]
    for key, block in summary.items():
        for n in names:
            s = block[n]
            L.append(f"| {key} | {n} | {_fmt(s['median_mae'])} | {_fmt(s['median_in_band'], 3)} | {_fmt(s['median_peak'], 3)} | "
                     f"{_fmt(s['median_recovery_s'], 1)} | {_fmt(s['recovered_frac'], 2)} | {s['hard_total']} | {s['overrides_total']} | {s['n']} |")
    L += ["", (f"Episode-level lower MAE under a second disturbance: Praxion v2 {wins['praxion_v2']} / relay re-tuned "
          f"{wins['relay_pi_retuned']} of {wins['n']} episodes."), "",
          "## Per run (median over scenarios)", "",
          "| run | plant seed | second | Praxion v2 MAE | relay re-tuned MAE | Praxion recovery s | relay recovery s | Praxion peak | relay peak |",
          "|---|---:|---|---:|---:|---:|---:|---:|---:|"]
    for r in runs:
        for second in conditions:
            key = second or "none"
            rows = [x for x in results if x["run_id"] == r["run_id"] and x["second"] == key]
            p = [x["controllers"]["praxion_v2"] for x in rows]
            q = [x["controllers"]["relay_pi_retuned"] for x in rows]
            L.append(f"| `{r['run_id']}` | {r['plant_seed']} | {key} | {_fmt(_med([c['mae'] for c in p]))} | {_fmt(_med([c['mae'] for c in q]))} | "
                     f"{_fmt(_med([c['recovery_s'] for c in p]), 1)} | {_fmt(_med([c['recovery_s'] for c in q]), 1)} | "
                     f"{_fmt(_med([c['peak_abs_err_after_second'] for c in p]), 3)} | {_fmt(_med([c['peak_abs_err_after_second'] for c in q]), 3)} |")
    Path(args.out + ".md").write_text("\n".join(L) + "\n")
    print("\n".join(L[:6 + len(conditions) * len(names)]))
    print(f"\nwrote {args.out}.json / .md in {time.time() - t0:.0f} s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
