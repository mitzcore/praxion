"""Exploration-seed validation of the classical relay baselines (evaluation/autotune.py). Never touches hidden seeds.

  uv run python scripts/validate_autotune.py [--seeds 1 20] [--families actuator_lag pump_derate ...]

Prints, per plant seed: the nominal tune (plant time, Pu, Ku, gains, nominal in-band on the plant-seed scenario) and,
per family, whether the shared detector fired, the re-identification (plant time, Pu, Ku, gains, hard-cutoff ticks)
and post-change MAE / in-band on the plant-seed scenario for nominal vs re-tuned vs the hand-tuned slow PID.
This is the evidence behind the frozen constants recorded in docs/IMPLEMENTATION_STATUS.md.
"""
from __future__ import annotations

import argparse
import statistics

from backend.controller.runtime import run_episode
from backend.evaluation import autotune as at
from backend.evaluation.baselines import SLOW_PID_TUNING, PIDController
from backend.evaluation.config import DISTURBANCE_AT_S, DISTURBANCE_EPISODE_S, EPISODE_S, SETTLE_S, TARGET
from backend.evaluation.metrics import compute_metrics
from backend.plant.tank_sim import TankSimulator
from backend.safety.supervisor import Supervisor
from backend.schemas import DisturbanceSpec


def _nominal(ctrl, seed):
    tr = run_episode(TankSimulator(), ctrl, Supervisor(), EPISODE_S, TARGET, seed)
    return compute_metrics(tr, SETTLE_S)


def _post(ctrl, seed, family):
    d = DisturbanceSpec(family=family, at_t=DISTURBANCE_AT_S)
    tr = run_episode(TankSimulator(), ctrl, Supervisor(), DISTURBANCE_EPISODE_S, TARGET, seed, disturbance=d)
    m = compute_metrics(tr, DISTURBANCE_AT_S + SETTLE_S)
    return m.mae, m.in_band_fraction, m.hard_violations


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", type=int, nargs=2, default=(1, 20), metavar=("FIRST", "LAST"))
    ap.add_argument("--families", nargs="+", default=["actuator_lag", "pump_derate", "extra_leak", "drain_shift"])
    args = ap.parse_args()
    seeds = list(range(args.seeds[0], args.seeds[1] + 1))

    print(f"rule {at.RULE}; hysteresis {at.HYSTERESIS}; relay d: stage1 {at.STAGE1_D}, stage2 {at.STAGE2_D}, "
          f"retune {at.RETUNE_D} (escalated {at.RETUNE_D_ESCALATED}); cycles {at.N_CYCLES}; retune cap {at.RETUNE_CAP_S:.0f} s")
    print("\n== nominal (plant-seed scenario)")
    print("seed | plant s | Pu | Ku | kp | ki | bias | source | in-band | MAE | hard ticks while tuning")
    nominal: dict[int, at.TuningReport] = {}
    inb_nom = []
    for s in seeds:
        rep = at.autotune_nominal(s)
        nominal[s] = rep
        src = next((x for x in rep.stages if x.stage == rep.source_estimate), rep.stages[0])
        m = _nominal(at.controller_from(rep), s)
        inb_nom.append(m.in_band_fraction)
        g = rep.gains
        print(f"{s:4d} | {rep.plant_s_total:6.1f} | {src.Pu or float('nan'):5.1f} | {src.Ku or float('nan'):6.2f} | {g['kp']:5.2f} | "
              f"{g['ki']:.3f} | {g['u_bias']:.2f} | {rep.source_estimate} | {m.in_band_fraction:.3f} | {m.mae:.4f} | {rep.hard_violations_total}")
    print(f"nominal in-band: min {min(inb_nom):.3f} median {statistics.median(inb_nom):.3f}; "
          f"plant s max {max(r.plant_s_total for r in nominal.values()):.0f}")

    for fam in args.families:
        print(f"\n== after change: {fam} (plant-seed scenario; detector = shared DegradationDetector)")
        print("seed | fired at | re-tuned | plant s (settle+relay) | Pu | Ku | kp | ki | bias | hard ticks | "
              "post MAE nominal / re-tuned / slow PID | post in-band nominal / re-tuned")
        fired = retuned = 0
        inb_re, plant_s = [], []
        for s in seeds:
            rep = at.autotune_after_change(s, fam, nominal[s])
            pn = _post(at.controller_from(nominal[s]), s, fam)
            pr = _post(at.controller_from(rep), s, fam)
            ps = _post(PIDController(**SLOW_PID_TUNING, name="slow_pid"), s, fam)
            fired += rep.detector_fired_at_s is not None
            retuned += rep.retuned
            inb_re.append(pr[1])
            if rep.retuned:
                plant_s.append(rep.plant_s_total)
            seg = rep.stages[-1] if rep.stages else None
            g = rep.gains
            fired_s = f"{rep.detector_fired_at_s:.1f}" if rep.detector_fired_at_s is not None else "silent"
            print(f"{s:4d} | {fired_s:>7} | "
                  f"{'yes' if rep.retuned else 'no':3} | {rep.plant_s_total:6.1f} ({rep.settle_s:.0f}+{rep.plant_s_total - rep.settle_s:.0f}) | "
                  f"{(seg.Pu if seg and seg.Pu else float('nan')):5.1f} | {(seg.Ku if seg and seg.Ku else float('nan')):5.2f} | "
                  f"{g['kp']:5.2f} | {g['ki']:.4f} | {g['u_bias']:.2f} | {rep.hard_violations_total:3d} | "
                  f"{pn[0]:.4f} / {pr[0]:.4f} / {ps[0]:.4f} | {pn[1]:.2f} / {pr[1]:.2f}"
                  + (f"  [{rep.fallback_reason}]" if rep.fallback_reason and rep.detector_fired_at_s is not None else ""))
        print(f"{fam}: detector fired {fired}/{len(seeds)}, re-tuned {retuned}/{len(seeds)}; re-tuned post in-band min "
              f"{min(inb_re):.3f} median {statistics.median(inb_re):.3f}"
              + (f"; relay plant s min {min(plant_s):.0f} max {max(plant_s):.0f}" if plant_s else ""))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
