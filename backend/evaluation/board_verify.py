"""On-board verification of model-authored controllers on the physical plant. TRUSTED.

The twin-scored Gate 3 says "v2 beats frozen v1 on a model of the changed machine". This module
measures the same claim directly on the board: each controller (by label, in the order the caller
chooses; counterbalancing is the caller's job) runs one closed-loop trial from a cooled start,
`pre_s` nominal seconds, then the change at t = pre_s, then `post_s` seconds. The change is either a
trusted actuator derate scheduled on the plant (`disturbance` given, at_t = pre_s) or applied by the
operator by hand (`disturbance=None`, `pause_for_operator` called at t = pre_s and
`pause_between_trials` called between trials so the operator can undo it).

Every trial is driven by `monitor.run_monitored_rollout`, the same tick loop the deployed controller
runs under (supervisor, exception containment, interlock path); nothing here re-implements it. Scores
use the frozen evaluator code: `metrics.post_disturbance_mae` (t >= pre_s) and
`metrics.compute_metrics` in-band from pre_s + profile.settle_s, the window the evaluator's
disturbance suites use (disturbance_at_s + settle_s). On hardware `h_true` is the reading itself.

The heater is idled (`plant.emergency_stop()`) after every trial and on any exception.
"""
from __future__ import annotations

import contextlib
import hashlib
import math
from collections.abc import Callable, Sequence
from typing import Any

from pydantic import BaseModel, Field

from backend.controller.protocol import Controller
from backend.evaluation.metrics import compute_metrics, post_disturbance_mae
from backend.evaluation.monitor import OperatorPause, run_monitored_rollout
from backend.plant.base import PlantAdapter
from backend.profiles import PlantProfile
from backend.safety.supervisor import Supervisor
from backend.schemas import DisturbanceSpec, Trace

EventCallback = Callable[..., None]
# (label, make_controller) or (label, make_controller, expected_sha256)
TrialSpec = tuple[str, Callable[[], Controller]] | tuple[str, Callable[[], Controller], str]

_TRIP_PREFIXES = ("interlock_high", "hard_cutoff")


class BoardVerificationError(RuntimeError):
    pass


class TrialResult(BaseModel):
    label: str
    controller_sha256: str
    start_T_display: float
    trace: Trace
    post_mae: float
    post_in_band: float
    overrides: int
    hard_violations: int
    invalid_outputs: int
    interlock_hit: bool  # any tick tripped the interlock or the hard cutoff (both cut the heater)
    operator_disturbance_at_s: float | None = None
    detector: dict[str, Any] = Field(default_factory=dict)


class BoardVerification(BaseModel):
    trials: list[TrialResult]
    order: list[str]
    pre_s: float
    post_s: float
    disturbance: dict[str, Any]
    comparison: dict[str, Any] = Field(default_factory=dict)
    scoring: dict[str, Any] = Field(default_factory=dict)
    fake_board: bool = False
    # Protocol-matched twin prediction, computed BEFORE the board trials (None + reason when unavailable).
    twin_prediction: dict[str, Any] | None = None
    twin_prediction_reason: str | None = None
    prediction_vs_board: dict[str, Any] = Field(default_factory=dict)


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _controller_sha(ctrl: Controller, expected: str | None, label: str) -> str:
    src = getattr(ctrl, "source", None)
    actual = _sha256(src) if isinstance(src, str) else None
    if expected is not None and actual is not None and actual != expected:
        raise BoardVerificationError(f"{label}: controller source sha256 {actual} != registered {expected}")
    sha = actual or expected
    if sha is None:
        raise BoardVerificationError(f"{label}: cannot determine controller sha256 (no source, none given)")
    return sha


def _comparison(trials: Sequence[Any]) -> dict[str, Any]:
    by = {t.label: t for t in trials}
    if "v1" not in by or "v2" not in by:
        return {}
    a, b = by["v1"].post_mae, by["v2"].post_mae
    red = (1.0 - b / a) if (math.isfinite(a) and math.isfinite(b) and abs(a) > 1e-12) else math.nan
    return {"post_mae_v1": a, "post_mae_v2": b, "reduction": red,
            "in_band_v1": by["v1"].post_in_band, "in_band_v2": by["v2"].post_in_band}


class TwinTrialResult(BaseModel):
    """A protocol-matched twin trial: the TrialResult fields minus start_T_display."""

    label: str
    controller_sha256: str
    trace: Trace
    post_mae: float
    post_in_band: float
    overrides: int
    hard_violations: int
    invalid_outputs: int
    interlock_hit: bool
    detector: dict[str, Any] = Field(default_factory=dict)


def _prediction_vs_board(pred: dict[str, Any], meas: dict[str, Any]) -> dict[str, Any]:
    if not pred or not meas:
        return {}
    out: dict[str, Any] = {k: {"predicted": pred.get(k), "measured": meas.get(k)}
                           for k in ("post_mae_v1", "post_mae_v2", "reduction", "in_band_v1", "in_band_v2")}
    rp, rm = pred.get("reduction"), meas.get("reduction")
    ok = all(isinstance(x, float) and math.isfinite(x) for x in (rp, rm))
    # direction: does the twin predict the same sign of the v1 -> v2 change the board measured?
    out["direction_agrees"] = bool(ok and ((rp > 0) == (rm > 0)))
    out["direction_definition"] = "sign(reduction predicted) == sign(reduction measured), reduction = 1 - mae_v2/mae_v1"
    return out


def run_board_verification(
    plant: PlantAdapter,
    trials: Sequence[TrialSpec],
    *,
    supervisor: Supervisor,
    profile: PlantProfile,
    pre_s: float,
    post_s: float,
    disturbance: DisturbanceSpec | None,
    pause_for_operator: OperatorPause | None = None,
    pause_between_trials: Callable[[], Any] | None = None,
    on_event: EventCallback | None = None,
    twin_factory: Callable[[], PlantAdapter] | None = None,
    prediction_basis: str | None = None,
    twin_missing_reason: str | None = None,
    cool_below_c: float = 30.0,
    cool_timeout_s: float = 600.0,
) -> BoardVerification:
    """Run each trial in order on ``plant`` and score it with the frozen evaluator metrics.

    ``twin_factory`` (optional): BEFORE any board trial, the same trials (same order, pre_s, post_s, same
    DisturbanceSpec at pre_s; operator mode schedules nothing on the twin) run on a fresh twin each,
    reset(seed=0, scenario=0), scored by the same code, stored as ``twin_prediction``. When it is None,
    ``twin_prediction`` is None and ``twin_prediction_reason`` says why (never skipped silently).
    """
    if disturbance is not None and abs(float(disturbance.at_t) - float(pre_s)) > 1e-9:
        raise ValueError(f"disturbance.at_t={disturbance.at_t} must equal pre_s={pre_s}")
    if disturbance is None and pause_for_operator is None:
        raise ValueError("operator mode (disturbance=None) needs pause_for_operator")
    labels = [t[0] for t in trials]
    if len(set(labels)) != len(labels):
        raise ValueError(f"duplicate trial labels: {labels}")
    if disturbance is not None and disturbance.magnitude is None:
        # Resolve the magnitude once so board and twin apply the identical derate (a twin would otherwise
        # draw its own seeded default).
        default = getattr(plant, "TRUSTED_DERATE_DEFAULT", None)
        if default is not None:
            disturbance = disturbance.model_copy(update={"magnitude": float(default)})

    def emit(kind: str, **payload: Any) -> None:
        if on_event is not None:
            on_event(kind, **payload)

    dt = plant.dt
    duration = float(pre_s) + float(post_s)
    calibrate_s = max(dt, float(pre_s) - dt)  # detector calibration must precede the change
    in_band_from = float(pre_s) + float(profile.settle_s)

    def one_trial(target_plant: PlantAdapter, sup: Supervisor, i: int, spec: TrialSpec,
                  pause: OperatorPause | None, tag: str) -> tuple[dict[str, Any], Any]:
        label, make = spec[0], spec[1]
        expected = spec[2] if len(spec) > 2 else None  # type: ignore[misc]
        ctrl = make()
        try:
            sha = _controller_sha(ctrl, expected, label)
            emit(f"{tag}_trial_started", label=label, index=i, controller_sha256=sha,
                 pre_s=float(pre_s), post_s=float(post_s))
            sup.reset_counters()
            res = run_monitored_rollout(
                target_plant, ctrl, sup, duration_s=duration, target=profile.target, seed=0, scenario=0,
                disturbance=disturbance, calibrate_s=calibrate_s, profile=profile,
                pause_for_operator=pause, disturbance_at_s=float(pre_s),
            )
        finally:
            with contextlib.suppress(Exception):
                ctrl.close()
            target_plant.emergency_stop()
        trace = res.trace
        op_t = trace.meta.get("operator_disturbance_at_s")
        # The post-change window is frozen at t >= pre_s for every trial (same window for v1 and v2);
        # the operator's confirmation time is recorded in meta, not used to move the window.
        trace.disturbance_at = float(pre_s)
        trace.meta["board_verification"] = {"label": label, "index": i, "plant": tag}
        m = compute_metrics(trace, in_band_from, band=profile.band, hard_cutoff=profile.hard_cutoff)
        fields = {
            "label": label, "controller_sha256": sha, "trace": trace, "post_mae": post_disturbance_mae(trace),
            "post_in_band": m.in_band_fraction, "overrides": m.override_count, "hard_violations": m.hard_violations,
            "invalid_outputs": m.invalid_outputs,
            "interlock_hit": any(s.reason.startswith(_TRIP_PREFIXES) for s in trace.steps),
            "detector": res.detector_state,
        }
        return fields, op_t

    # ---- twin prediction first (no hardware involved)
    twin_prediction: dict[str, Any] | None = None
    twin_reason = twin_missing_reason
    if twin_factory is not None:
        twin_results: list[TwinTrialResult] = []
        for i, spec in enumerate(trials):
            fields, _ = one_trial(twin_factory(), Supervisor(supervisor.limits), i, spec, None, "twin")
            twin_results.append(TwinTrialResult(**fields))
        twin_prediction = {"prediction_basis": prediction_basis,
                           "trials": [t.model_dump(mode="json") for t in twin_results],
                           "comparison": _comparison(twin_results)}
        twin_reason = None
    elif twin_reason is None:
        twin_reason = "no twin_factory given"

    # ---- board trials
    # Same start state for every trial: a physical plant's reset() waits for COOL_BELOW_C (default 35 °C,
    # 120 s ceiling, tuned for a cold start). Between A/B trials the board comes down from the band, so wait
    # for a lower temperature with a longer ceiling; otherwise the second controller starts warmer and the
    # comparison is biased. Restored afterwards. The start temperature of each trial is recorded regardless.
    results: list[TrialResult] = []
    physical = bool(getattr(plant, "is_physical", False))
    saved_cool = (getattr(plant, "COOL_BELOW_C", None), getattr(plant, "COOL_TIMEOUT_S", None))
    if physical:
        plant.COOL_BELOW_C = float(cool_below_c)  # type: ignore[attr-defined]
        plant.COOL_TIMEOUT_S = float(cool_timeout_s)  # type: ignore[attr-defined]
    try:
        for i, spec in enumerate(trials):
            if i > 0 and pause_between_trials is not None:
                plant.emergency_stop()
                pause_between_trials()
            fields, op_t = one_trial(plant, supervisor, i, spec,
                                     pause_for_operator if disturbance is None else None, "board")
            start_y = fields["trace"].steps[0].y if fields["trace"].steps else math.nan
            tr = TrialResult(**fields, start_T_display=profile.to_display(start_y), operator_disturbance_at_s=op_t)
            results.append(tr)
            emit("board_trial_finished", label=tr.label, index=i, controller_sha256=tr.controller_sha256,
                 post_mae=tr.post_mae, post_in_band=tr.post_in_band, overrides=tr.overrides,
                 hard_violations=tr.hard_violations, invalid_outputs=tr.invalid_outputs,
                 interlock_hit=tr.interlock_hit, start_T_display=tr.start_T_display,
                 operator_disturbance_at_s=op_t, n_steps=len(tr.trace.steps))
    except BaseException:
        with contextlib.suppress(Exception):
            plant.emergency_stop()
        raise
    finally:
        if physical:
            plant.COOL_BELOW_C, plant.COOL_TIMEOUT_S = saved_cool  # type: ignore[attr-defined]
    if disturbance is not None:
        dist = {"family": disturbance.family, "magnitude": disturbance.magnitude, "applied_by": "trusted_actuator",
                "at_t": float(pre_s)}
    else:
        dist = {"family": None, "magnitude": None, "applied_by": "operator", "at_t": float(pre_s)}
    comparison = _comparison(results)
    pvb = _prediction_vs_board(twin_prediction["comparison"], comparison) if twin_prediction else {}
    out = BoardVerification(
        trials=results, order=labels, pre_s=float(pre_s), post_s=float(post_s), disturbance=dist,
        comparison=comparison,
        scoring={"post_mae": "metrics.post_disturbance_mae over t >= pre_s",
                 "post_in_band": f"metrics.compute_metrics in_band_fraction over t >= pre_s + settle_s "
                                 f"({in_band_from:.0f} s), band {list(profile.band)}",
                 "h_true_on_hardware": "the sensor reading (no hidden truth on hardware)",
                 "profile": profile.name,
                 "board_start_state": f"reset waits for T1 < {cool_below_c:g} °C (ceiling {cool_timeout_s:g} s) before each trial"},
        twin_prediction=twin_prediction, twin_prediction_reason=twin_reason, prediction_vs_board=pvb,
    )
    emit("board_verification", order=labels, disturbance=dist, comparison=comparison,
         twin_prediction_basis=prediction_basis if twin_prediction else None,
         twin_prediction_reason=twin_reason, prediction_vs_board=pvb,
         trials=[{"label": t.label, "controller_sha256": t.controller_sha256, "post_mae": t.post_mae,
                  "post_in_band": t.post_in_band, "interlock_hit": t.interlock_hit} for t in results])
    return out
