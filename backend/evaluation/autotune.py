"""Classical self-tuning baseline: Åström–Hägglund relay auto-tuning → Tyreus–Luyben PI. TRUSTED, scoring only.

NEVER shown to the model (CLAUDE.md rule 1). This is the fair classical rival the competitive review asked
for (docs/COMPETITIVE_LANDSCAPE.md): a fully automatic identify-then-design controller that gets the same
plant access as Praxion's agent and re-identifies when the SAME degradation detector fires.

Two variants, mirroring the two Praxion rows in the ablation tables:

* ``autotune_nominal``   — relay feedback on the nominal machine (reset(plant_seed), the agent's discovery start
  state), two stages: a full relay (u ∈ {0, 1}) to find the operating point, then a symmetric relay of smaller
  amplitude around it for a clean ultimate-point estimate. Rival of "Muse v1 frozen".
* ``autotune_after_change`` — deploy the nominal PI, run the frozen monitored rollout with the family disturbance
  (same detector, calibration and timing as Praxion's live run), and when the detector fires: hold the pre-change
  input until the level settles, then a small-amplitude bias-seeking relay on the changed machine, then redesign.
  If the detector never fires the nominal gains are kept, exactly as Praxion retains v1. Rival of "Full Praxion".

Fairness notes a reviewer should know (all reported in the tuning report and the benchmark notes):
* The relay switches in closed loop at the control period; the agent's experiment API only allows constant holds.
  That is MORE access than the agent has, in the classical method's favour.
* Plant time is capped generously (``RETUNE_CAP_S`` = 600 s vs the agent's after-change budget of 160 s) and the
  seconds actually used are reported next to Praxion's. The relay needs about 300–400 s under a 20 s delay.
* Every frozen constant below was chosen on EXPLORATION seeds 1–20 only (2026-11-01, see IMPLEMENTATION_STATUS),
  before any hidden-seed scoring. The tuning rule was picked by a pre-stated criterion: the rule with the highest
  worst-case in-band fraction over both phases (nominal and re-tuned), tie broken by nominal median MAE.
  Measured on seeds 1–20: ZN-PI 0.858, ZN-PID 0.912, TL-PI 1.000, TL-PID 1.000; TL-PI nominal MAE 0.0011 vs 0.0013.
* Timing constants (dwell, stuck test, settle) are tank-scale. The benchmark table is tank-only.
"""
from __future__ import annotations

import itertools
import math
from collections.abc import Callable
from typing import Any, Literal

import numpy as np
from pydantic import BaseModel, Field

from backend.agent.session import Budget
from backend.controller.runtime import _apply
from backend.evaluation.baselines import PIDController
from backend.evaluation.monitor import DegradationDetector, run_monitored_rollout
from backend.plant.base import PlantAdapter
from backend.plant.tank_sim import TankSimulator
from backend.profiles import TANK, PlantProfile
from backend.safety.supervisor import SafetyLimits, Supervisor
from backend.schemas import DisturbanceSpec

# ------------------------------------------------------------------------------------------------ FROZEN
RULE = "tl_pi"
HYSTERESIS = 0.015          # > max sensor noise std (0.010); relay switches outside ±HYSTERESIS of target
STAGE1_D = 0.5              # full relay, u ∈ {0, 1}: finds the operating point (mean u) and a first ultimate point
STAGE2_D = 0.2              # symmetric relay around the operating point
RETUNE_D = 0.1              # after a change the loop may have a long delay: 0.2 overflowed on half the seeds
RETUNE_D_ESCALATED = 0.15   # one escalation if the small relay does not oscillate measurably
N_CYCLES = 3                # up-switch intervals after the first switch; the approach interval is discarded,
                            # so N_CYCLES - 1 clean periods are averaged (consistency reported as Pu_cv)
A_MIN = 0.03                # minimum oscillation amplitude (2 × HYSTERESIS) for a usable estimate
SMOOTH_S = 0.5              # moving average used only for amplitude extraction
DWELL_S = 1.0               # minimum time between switches (noise chatter guard)
STUCK_AFTER_S = 45.0        # longer than a half-period under the 20 s delay, so a legitimate cycle never trips it
SLOPE_WINDOW_S = 10.0
SLOPE_MIN = 2e-4            # level must move toward the setpoint at least this fast (per s) or the bias shifts
BIAS_STEP = 0.05
SETTLE_MAX_S = 60.0
SETTLE_TOL = 0.04
RETUNE_CAP_S = 600.0        # generous; the agent's after-change budget is 4 × 40 s = 160 s (reported side by side)

TUNING_RULES: dict[str, tuple[float, float, float]] = {
    # name: (Kp / Ku, Ti / Pu, Td / Pu)
    "zn_pi": (0.45, 1 / 1.2, 0.0),
    "zn_pid": (0.6, 0.5, 0.125),
    "tl_pi": (1 / 3.2, 2.2, 0.0),
    "tl_pid": (1 / 2.2, 2.2, 1 / 6.3),
}


class RelayEstimate(BaseModel):
    """One relay-feedback segment and what it measured."""

    stage: str
    d: float
    bias_start: float
    bias_end: float
    ok: bool
    cycles: int
    plant_s: float
    Pu: float | None = None
    Pu_cv: float | None = None       # std/mean of the measured periods (consistency)
    a: float | None = None           # oscillation amplitude (smoothed y)
    Ku: float | None = None
    mean_u: float | None = None      # mean applied u over the measured cycles = operating-point estimate
    bias_changes: int = 0
    overrides: int = 0
    hard_violations: int = 0         # hard-cutoff / interlock ticks during this segment
    max_y: float
    min_y: float
    warnings: list[str] = Field(default_factory=list)


class TuningReport(BaseModel):
    kind: Literal["nominal", "retuned"]
    plant_seed: int
    family: str | None = None
    rule: str = RULE
    gains: dict[str, float]                      # kp, ki, kd, u_bias (PIDController kwargs)
    stages: list[RelayEstimate] = Field(default_factory=list)
    plant_s_total: float                         # identification plant time (settle + relay segments)
    budget_s: float                              # the agent's comparable budget
    cap_s: float
    retuned: bool = False                        # after-change only: did a re-identification happen
    detector_fired_at_s: float | None = None     # plant time of detection (None if it never fired)
    disturbance_at_s: float | None = None
    settle_s: float = 0.0
    settle_hard_violations: int = 0
    nominal_gains: dict[str, float] | None = None
    fallback_reason: str | None = None
    source_estimate: str | None = None           # which stage's (Ku, Pu) produced the gains

    @property
    def hard_violations_total(self) -> int:
        return self.settle_hard_violations + sum(s.hard_violations for s in self.stages)


def tuning_rule(Ku: float, Pu: float, rule: str = RULE) -> dict[str, float]:
    kp_f, ti_f, td_f = TUNING_RULES[rule]
    kp = kp_f * Ku
    ti = ti_f * Pu
    td = td_f * Pu
    return {"kp": kp, "ki": kp / ti if ti > 0 else 0.0, "kd": kp * td}


def _is_hard(reason: str) -> bool:
    return reason.startswith("hard_cutoff") or reason == "interlock_high"


# ------------------------------------------------------------------------------------------------ relay core
def relay_segment(
    plant: PlantAdapter, sup: Supervisor, *, target: float, d: float, bias: float, stage: str,
    max_s: float, n_cycles: int = N_CYCLES, bias_seeking: bool = False,
) -> RelayEstimate:
    """Relay feedback on a LIVE plant (no reset). u = bias ± d with hysteresis around ``target``.

    With ``bias_seeking`` the bias shifts by BIAS_STEP when, STUCK_AFTER_S after a switch, the level is not moving
    toward the setpoint (the relay states do not bracket the operating point); cycle counting restarts."""
    dt = plant.dt

    def states(b: float) -> tuple[float, float]:
        return min(1.0, b + d), max(0.0, b - d)

    bias_start = bias
    u_hi, u_lo = states(bias)
    obs = plant.observe()
    u = u_hi if target - obs.y >= 0 else u_lo
    switches: list[tuple[float, int]] = []
    ts: list[float] = []
    ys: list[float] = []
    us: list[float] = []
    overrides = hard = 0
    last_sw = obs.t
    bias_changes = 0
    nw = max(3, int(SLOPE_WINDOW_S / dt))
    for _ in range(round(max_s / dt)):
        obs = plant.observe()
        e = target - obs.y
        if obs.t - last_sw >= DWELL_S:
            if e > HYSTERESIS and u != u_hi:
                u, last_sw = u_hi, obs.t
                switches.append((obs.t, +1))
            elif e < -HYSTERESIS and u != u_lo:
                u, last_sw = u_lo, obs.t
                switches.append((obs.t, -1))
        if bias_seeking and obs.t - last_sw > STUCK_AFTER_S and len(ys) > nw:
            recent = float(np.mean(ys[-nw // 3:]))
            earlier = float(np.mean(ys[-nw:-2 * nw // 3]))
            slope = (recent - earlier) / (SLOPE_WINDOW_S * 2 / 3)
            toward = slope > SLOPE_MIN if u == u_hi else slope < -SLOPE_MIN
            if not toward:
                bias = min(max(bias + (BIAS_STEP if u == u_hi else -BIAS_STEP), 0.05 + d), 0.95 - d)
                u_hi, u_lo = states(bias)
                u = u_hi if e > 0 else u_lo
                switches, bias_changes, last_sw = [], bias_changes + 1, obs.t
        dec = sup.filter(u, obs, now_t=obs.t)
        overrides += int(dec.override)
        hard += int(_is_hard(dec.reason))
        _apply(plant, dec.u_applied, dec.reason)  # same trip handling as the trusted runtime (e-stop flush)
        ts.append(obs.t)
        ys.append(obs.y)
        us.append(dec.u_applied)
        if sum(1 for _, s in switches if s > 0) >= n_cycles + 1:
            break
    t_arr, y_arr, u_arr = np.asarray(ts), np.asarray(ys), np.asarray(us)
    ups = [t for t, s in switches if s > 0]
    est = RelayEstimate(stage=stage, d=d, bias_start=bias_start, bias_end=bias,
                        ok=False, cycles=max(0, len(ups) - 1), plant_s=round(len(ts) * dt, 3), bias_changes=bias_changes,
                        overrides=overrides, hard_violations=hard,
                        max_y=float(y_arr.max()) if len(y_arr) else math.nan,
                        min_y=float(y_arr.min()) if len(y_arr) else math.nan)
    if len(ups) < 3:
        est.warnings.append(f"only {len(ups)} up-switches in {est.plant_s:.0f} s; need >= 3 for a period estimate")
        return est
    periods = np.diff(ups[1:])  # discard the approach cycle
    est.Pu = float(np.mean(periods))
    est.Pu_cv = float(np.std(periods) / np.mean(periods)) if len(periods) > 1 else 0.0
    k = max(1, round(SMOOTH_S / dt))
    amps = []
    for t0, t1 in itertools.pairwise(ups[1:]):
        m = (t_arr >= t0) & (t_arr < t1)
        yy = y_arr[m]
        ysm = np.convolve(yy, np.ones(k) / k, mode="valid") if len(yy) > k else yy
        amps.append((ysm.max() - ysm.min()) / 2)
    est.a = float(np.median(amps))
    m = (t_arr >= ups[1]) & (t_arr < ups[-1])
    est.mean_u = float(u_arr[m].mean())
    if est.a < A_MIN:
        est.warnings.append(f"amplitude {est.a:.4f} < {A_MIN} (comparable to hysteresis): estimate unusable")
        return est
    est.Ku = 4 * d / (math.pi * math.sqrt(max(est.a**2 - HYSTERESIS**2, 1e-12)))
    if est.Pu_cv is not None and est.Pu_cv > 0.25:
        est.warnings.append(f"period inconsistent (cv {est.Pu_cv:.2f})")
    est.ok = True
    return est


def settle_hold(plant: PlantAdapter, sup: Supervisor, *, target: float, u_hold: float,
                max_s: float = SETTLE_MAX_S, tol: float = SETTLE_TOL) -> tuple[float, int]:
    """Hold a steady input until the level is within ``tol`` of target and nearly flat, or ``max_s``.
    Returns (plant seconds, hard-cutoff ticks). After a violently oscillating loop the delay line still holds
    saturated commands; those consequences are inherited here and counted honestly."""
    dt = plant.dt
    ys: list[float] = []
    hard = 0
    n = max(4, int(10.0 / dt))
    for _ in range(int(max_s / dt)):
        obs = plant.observe()
        dec = sup.filter(u_hold, obs, now_t=obs.t)
        hard += int(_is_hard(dec.reason))
        _apply(plant, dec.u_applied, dec.reason)
        ys.append(obs.y)
        if len(ys) > n and abs(ys[-1] - target) < tol and abs(np.mean(ys[-n // 2:]) - np.mean(ys[-n:-n // 2])) < 0.01:
            break
    return round(len(ys) * dt, 3), hard


# ------------------------------------------------------------------------------------------------ public API
def autotune_nominal(plant_seed: int, *, plant_factory: Callable[[], PlantAdapter] = TankSimulator,
                     profile: PlantProfile = TANK, limits: SafetyLimits | None = None) -> TuningReport:
    """Two-stage relay auto-tune on the nominal machine, from the agent's discovery start state."""
    plant = plant_factory()
    sup = Supervisor(limits)
    plant.reset(plant_seed)
    cap = profile.max_experiments * profile.max_single_experiment_s  # the agent's discovery budget
    target = profile.target
    s1 = relay_segment(plant, sup, target=target, d=STAGE1_D, bias=0.5, stage="stage1_full_relay", max_s=cap)
    stages = [s1]
    src = s1
    remaining = cap - s1.plant_s
    if s1.ok and remaining > 0:
        bias2 = min(max(float(s1.mean_u), STAGE2_D + 0.02), 1.0 - STAGE2_D - 0.02)
        s2 = relay_segment(plant, sup, target=target, d=STAGE2_D, bias=bias2, stage="stage2_symmetric_relay", max_s=remaining)
        stages.append(s2)
        if s2.ok:
            src = s2
        else:
            s2.warnings.append("stage 2 unusable; gains from stage 1")
    rep = TuningReport(kind="nominal", plant_seed=plant_seed, gains={}, stages=stages, budget_s=cap, cap_s=cap,
                       plant_s_total=round(sum(s.plant_s for s in stages), 3))
    if not src.ok:
        rep.fallback_reason = "relay did not produce a usable ultimate-point estimate within the budget"
        rep.gains = {"kp": 0.0, "ki": 0.0, "kd": 0.0, "u_bias": float(s1.mean_u or 0.5)}
        return rep
    g = tuning_rule(float(src.Ku), float(src.Pu), RULE)
    g["u_bias"] = float(src.mean_u)
    rep.gains = g
    rep.source_estimate = src.stage
    return rep


def autotune_after_change(plant_seed: int, family: str | None, nominal: TuningReport, *,
                          plant_factory: Callable[[], PlantAdapter] = TankSimulator, profile: PlantProfile = TANK,
                          limits: SafetyLimits | None = None) -> TuningReport:
    """Deploy the nominal PI under the frozen monitored rollout with ``family`` applied at ``profile.monitor_pre_s``
    (plant-seed scenario, as in Praxion's live run). If the shared detector fires: settle, relay, redesign.
    Otherwise keep the nominal gains (no re-tune), the same rule Praxion applies to v1."""
    plant = plant_factory()
    sup = Supervisor(limits)
    ctrl = controller_from(nominal)
    det = DegradationDetector(plant.dt, window_s=profile.monitor_window_s, factor=profile.monitor_factor,
                              floor=profile.monitor_floor, hold_s=profile.monitor_hold_s)
    spec = DisturbanceSpec(family=family, at_t=profile.monitor_pre_s) if family else None  # type: ignore[arg-type]
    res = run_monitored_rollout(plant, ctrl, sup, duration_s=profile.monitor_duration_s, target=profile.target,
                                seed=plant_seed, disturbance=spec, calibrate_s=profile.monitor_calibrate_s, detector=det,
                                stop_after_detection_s=profile.monitor_post_detection_s, profile=profile)
    rep = TuningReport(kind="retuned", plant_seed=plant_seed, family=family, gains=dict(nominal.gains),
                       nominal_gains=dict(nominal.gains), plant_s_total=0.0,
                       budget_s=Budget().max_reidentification_experiments * profile.after_change_max_single_experiment_s,
                       cap_s=RETUNE_CAP_S,
                       detector_fired_at_s=res.degraded_at_t, disturbance_at_s=profile.monitor_pre_s)
    if res.degraded_at_t is None:
        rep.fallback_reason = "monitor did not fire on the plant-seed scenario; nominal gains kept (no re-tune)"
        return rep
    tr = res.trace
    t, u = tr.times(), tr.u_applied()
    cal = profile.monitor_calibrate_s
    win = (t >= cal - 30.0) & (t < cal)
    bias0 = float(u[win].mean()) if win.any() else float(nominal.gains.get("u_bias", 0.5))
    target = profile.target
    settle_s, settle_hard = settle_hold(plant, sup, target=target, u_hold=min(max(bias0, 0.05), 0.95))
    rep.settle_s, rep.settle_hard_violations = settle_s, settle_hard
    used = settle_s
    seg = relay_segment(plant, sup, target=target, d=RETUNE_D, bias=min(max(bias0, RETUNE_D + 0.05), 0.95 - RETUNE_D),
                        stage="retune_relay", max_s=RETUNE_CAP_S - used, bias_seeking=True)
    rep.stages.append(seg)
    used += seg.plant_s
    if not seg.ok and RETUNE_CAP_S - used > 60.0:
        seg2 = relay_segment(plant, sup, target=target, d=RETUNE_D_ESCALATED, bias=seg.bias_end, stage="retune_relay_escalated",
                             max_s=RETUNE_CAP_S - used, bias_seeking=True)
        rep.stages.append(seg2)
        used += seg2.plant_s
        seg = seg2 if seg2.ok else seg
    rep.plant_s_total = round(used, 3)
    if not seg.ok:
        rep.fallback_reason = f"relay re-identification failed within {RETUNE_CAP_S:.0f} s; nominal gains kept"
        return rep
    g = tuning_rule(float(seg.Ku), float(seg.Pu), RULE)
    g["u_bias"] = float(seg.mean_u)
    rep.gains = g
    rep.retuned = True
    rep.source_estimate = seg.stage
    return rep


def controller_from(report: TuningReport) -> PIDController:
    name = "baseline_relay_pi" if report.kind == "nominal" else f"baseline_relay_pi_retuned:{report.family}"
    g = report.gains
    return PIDController(kp=g["kp"], ki=g["ki"], kd=g.get("kd", 0.0), u_bias=g.get("u_bias", 0.0), name=name)


def summary_note(report: TuningReport) -> str:
    """One line for the benchmark tables."""
    g = report.gains
    gains = f"kp={g['kp']:.2f} ki={g['ki']:.4f} bias={g.get('u_bias', 0.0):.2f}"
    if report.kind == "nominal":
        if report.fallback_reason:
            return f"relay auto-tune FAILED: {report.fallback_reason}"
        return (f"relay auto-tune on the nominal machine, {report.plant_s_total:.0f} s plant time "
                f"(agent discovery budget {report.budget_s:.0f} s); {RULE.upper().replace('_', '-')} {gains}; "
                f"{report.hard_violations_total} hard-cutoff ticks while identifying")
    if report.detector_fired_at_s is None:
        return "shared monitor did not fire on the plant-seed scenario, so no re-tune: nominal gains kept (same rule as Praxion)"
    fired = report.detector_fired_at_s - (report.disturbance_at_s or 0.0)
    if not report.retuned:
        return f"monitor fired {fired:.0f} s after the change but {report.fallback_reason}"
    return (f"monitor fired {fired:.0f} s after the change; settle {report.settle_s:.0f} s + relay "
            f"{report.plant_s_total - report.settle_s:.0f} s plant time (agent after-change budget {report.budget_s:.0f} s); "
            f"{gains}; {report.hard_violations_total} hard-cutoff ticks while identifying")


def report_dict(report: TuningReport) -> dict[str, Any]:
    d = report.model_dump()
    d["hard_violations_total"] = report.hard_violations_total
    d["note"] = summary_note(report)
    return d
