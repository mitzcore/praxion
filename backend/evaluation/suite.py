"""Independent evaluator (plan sections 9 and 10). TRUSTED.

Runs OUTSIDE any sandbox. Scores candidates on evaluator-only seeds using simulator truth
(``h_true``) via ``evaluation/metrics.py``. Everything produced here is trusted; the only
projection that may reach the agent is ``EvaluationReport.agent_safe()``.

Controllers arrive as zero-arg factories (``Callable[[], Controller]``). The factory is called
ONCE per report (sandboxed controllers are expensive to start); ``run_episode`` resets the
controller before every episode, and this module closes it at the end of the report.
"""
from __future__ import annotations

import contextlib
import math
import statistics
from collections.abc import Callable, Sequence
from typing import Any

from backend.controller.protocol import Controller
from backend.controller.runtime import run_episode
from backend.evaluation.baselines import OnOffController, PIDController
from backend.evaluation.config import (
    DISTURBANCE_AT_S,
    DISTURBANCE_EPISODE_S,
    DISTURBANCE_SEEDS,
    EPISODE_S,
    GATE2_MIN_INBAND,
    GATE2_MIN_PASS,
    GATE3_MIN_MAE_REDUCTION,
    GATE3_MIN_PASS,
    HELDOUT_SEEDS,
    SETTLE_S,
    TARGET,
)
from backend.evaluation.metrics import compute_metrics, post_disturbance_mae
from backend.evaluation.report import EpisodeResult, EvaluationReport
from backend.plant.base import PlantAdapter
from backend.plant.tank_sim import TankSimulator
from backend.safety.supervisor import SafetyLimits, Supervisor
from backend.schemas import DisturbanceSpec, Metrics, Trace

ControllerFactory = Callable[[], Controller]
PlantFactory = Callable[[], PlantAdapter]

_MAE_EPS = 1e-9


# --------------------------------------------------------------------------- helpers
def _median(xs: Sequence[float]) -> float:
    vals = [float(x) for x in xs if x is not None and math.isfinite(float(x))]
    return float(statistics.median(vals)) if vals else math.nan


def _mean(xs: Sequence[float]) -> float:
    vals = [float(x) for x in xs if x is not None and math.isfinite(float(x))]
    return float(statistics.fmean(vals)) if vals else math.nan


def _run_one(
    controller: Controller,
    *,
    plant_seed: int,
    scenario: int,
    duration_s: float,
    disturbance: DisturbanceSpec | None,
    plant_factory: PlantFactory,
    limits: SafetyLimits | None,
) -> tuple[Trace, dict[str, Any] | None]:
    """One episode (machine ``plant_seed``, episode ``scenario``) on a fresh plant and a fresh
    supervisor, so override / violation counts never bleed between episodes."""
    plant = plant_factory()
    supervisor = Supervisor(limits)
    supervisor.reset_counters()
    trace = run_episode(
        plant, controller, supervisor, duration_s, TARGET, plant_seed,
        scenario=scenario, disturbance=disturbance, close_after=False,
    )
    hidden = getattr(plant, "hidden_params", None)
    audit = hidden() if callable(hidden) else None
    return trace, audit


def _heldout_verdict(m: Metrics) -> tuple[bool, list[str]]:
    reasons: list[str] = []
    if m.invalid_outputs != 0:
        reasons.append(f"invalid_outputs={m.invalid_outputs} (must be 0)")
    if m.hard_violations != 0:
        reasons.append(f"hard_violations={m.hard_violations} (must be 0)")
    if m.override_count != 0:
        reasons.append(f"override_count={m.override_count} (must be 0)")
    inb = m.in_band_fraction
    if not (math.isfinite(inb) and inb >= GATE2_MIN_INBAND):
        reasons.append(f"in_band_fraction={inb:.3f} < {GATE2_MIN_INBAND:.2f}")
    return not reasons, reasons


def _disturbance_verdict(m: Metrics) -> tuple[bool, list[str]]:
    reasons: list[str] = []
    if m.invalid_outputs != 0:
        reasons.append(f"invalid_outputs={m.invalid_outputs} (must be 0)")
    if m.hard_violations != 0:
        reasons.append(f"hard_violations={m.hard_violations} (must be 0)")
    return not reasons, reasons


def _base_aggregate(episodes: list[EpisodeResult]) -> dict[str, float]:
    ms = [e.metrics for e in episodes]
    return {
        "n_episodes": float(len(episodes)),
        "n_passed": float(sum(1 for e in episodes if e.passed)),
        "median_mae": _median([m.mae for m in ms]),
        "mean_in_band_fraction": _mean([m.in_band_fraction for m in ms]),
        "median_actuation_energy": _median([m.actuation_energy for m in ms]),
        "total_overrides": float(sum(m.override_count for m in ms)),
        "total_hard_violations": float(sum(m.hard_violations for m in ms)),
        "total_invalid_outputs": float(sum(m.invalid_outputs for m in ms)),
    }


def _run_suite(
    factory: ControllerFactory,
    *,
    plant_seed: int,
    seeds: Sequence[int],
    duration_s: float,
    scored_from_s: float,
    family: str | None,
    verdict: Callable[[Metrics], tuple[bool, list[str]]],
    plant_factory: PlantFactory,
    limits: SafetyLimits | None,
) -> tuple[list[EpisodeResult], list[dict[str, Any]]]:
    """Run every scenario seed on machine ``plant_seed`` with ONE controller instance
    (factory called once, closed in finally). EpisodeResult.seed stores the SCENARIO."""
    controller = factory()
    episodes: list[EpisodeResult] = []
    audit: list[dict[str, Any]] = []
    try:
        for index, seed in enumerate(seeds):
            dist = DisturbanceSpec(family=family, at_t=DISTURBANCE_AT_S) if family is not None else None
            trace, hidden = _run_one(
                controller,
                plant_seed=plant_seed,
                scenario=seed,
                duration_s=duration_s,
                disturbance=dist,
                plant_factory=plant_factory,
                limits=limits,
            )
            metrics = compute_metrics(trace, scored_from_s)
            passed, reasons = verdict(metrics)
            episodes.append(
                EpisodeResult(
                    index=index,
                    seed=seed,
                    disturbance_family=family,
                    metrics=metrics,
                    trace=trace,
                    passed=passed,
                    fail_reasons=reasons,
                )
            )
            audit.append({"index": index, "plant_seed": plant_seed, "scenario": seed,
                          "controller": getattr(controller, "name", "?"), "hidden_params": hidden})
    finally:
        with contextlib.suppress(Exception):  # closing a broken candidate must not mask results
            controller.close()
    return episodes, audit


def _baseline_block(
    name: str,
    factory: ControllerFactory,
    *,
    plant_seed: int,
    seeds: Sequence[int],
    duration_s: float,
    scored_from_s: float,
    family: str | None,
    verdict: Callable[[Metrics], tuple[bool, list[str]]],
    plant_factory: PlantFactory,
    limits: SafetyLimits | None,
) -> tuple[dict[str, Any], dict[str, float], list[dict[str, Any]]]:
    """Run a baseline through the same seeds. Returns (comparison block, prefixed aggregate, audit)."""
    eps, audit = _run_suite(
        factory, plant_seed=plant_seed, seeds=seeds, duration_s=duration_s, scored_from_s=scored_from_s, family=family,
        verdict=verdict, plant_factory=plant_factory, limits=limits,
    )
    agg = _base_aggregate(eps)
    per_seed: list[dict[str, Any]] = []
    for e in eps:
        row: dict[str, Any] = {"index": e.index, "plant_seed": plant_seed, "scenario": e.seed, "passed": e.passed,
                               "metrics": e.metrics.model_dump()}
        if family is not None:
            row["post_disturbance_mae"] = post_disturbance_mae(e.trace)
        per_seed.append(row)
    if family is not None:
        agg["median_post_disturbance_mae"] = _median([r["post_disturbance_mae"] for r in per_seed])
    block = {"name": name, "per_seed": per_seed, "aggregate": agg}
    prefixed = {f"{name}_{k}": v for k, v in agg.items()}
    return block, prefixed, audit


# --------------------------------------------------------------------------- public API
def evaluate_heldout(
    factory: ControllerFactory,
    *,
    candidate_id: str,
    plant_seed: int,
    plant_factory: PlantFactory = TankSimulator,
    limits: SafetyLimits | None = None,
) -> EvaluationReport:
    """Gate 2 on machine ``plant_seed``: one nominal episode per HELDOUT_SEEDS SCENARIO, scored after SETTLE_S on h_true.

    An episode passes iff invalid_outputs == 0, hard_violations == 0, override_count == 0 and
    in_band_fraction >= GATE2_MIN_INBAND. The gate passes iff >= GATE2_MIN_PASS episodes pass.
    Fixed PID and on/off baselines run through the same seeds for comparison (trusted only).
    """
    common: dict[str, Any] = {
        "plant_seed": plant_seed, "seeds": HELDOUT_SEEDS, "duration_s": EPISODE_S, "scored_from_s": SETTLE_S, "family": None,
        "verdict": _heldout_verdict, "plant_factory": plant_factory, "limits": limits,
    }
    episodes, audit = _run_suite(factory, **common)
    aggregate = _base_aggregate(episodes)
    n_passed = int(aggregate["n_passed"])
    gate_passed = n_passed >= GATE2_MIN_PASS
    gate_reasons = [
        (
            f"{n_passed}/{len(episodes)} episodes passed (need >= {GATE2_MIN_PASS}): "
            f"valid outputs, zero hard violations, zero overrides, in-band >= {GATE2_MIN_INBAND:.2f} "
            f"after {SETTLE_S:.0f} s"
        ),
        "G2 passed" if gate_passed else "G2 failed",
    ]
    comparison: dict[str, Any] = {}
    for name, bfactory in (("baseline_pid", PIDController), ("baseline_onoff", OnOffController)):
        block, prefixed, b_audit = _baseline_block(name, bfactory, **common)
        comparison[name] = block
        aggregate.update(prefixed)
        audit.extend(b_audit)
    comparison["audit"] = audit
    return EvaluationReport(
        candidate_id=candidate_id,
        suite="heldout",
        episodes=episodes,
        aggregate=aggregate,
        gate_name="G2",
        gate_passed=gate_passed,
        gate_reasons=gate_reasons,
        comparison=comparison,
    )


def evaluate_disturbance(
    factory: ControllerFactory,
    family: str,
    *,
    candidate_id: str,
    plant_seed: int,
    plant_factory: PlantFactory = TankSimulator,
    limits: SafetyLimits | None = None,
) -> EvaluationReport:
    """Disturbance suite on machine ``plant_seed``: one episode per DISTURBANCE_SEEDS SCENARIO with ``family`` at DISTURBANCE_AT_S.

    Metrics are scored from DISTURBANCE_AT_S + SETTLE_S. An episode passes iff it is safe
    (invalid_outputs == 0 and hard_violations == 0); overrides are allowed but counted.
    Post-disturbance MAE per episode is stored in ``comparison["post_disturbance_mae"]``
    keyed by ``str(index)`` (string keys so the report round-trips through JSON).
    """
    common: dict[str, Any] = {
        "plant_seed": plant_seed, "seeds": DISTURBANCE_SEEDS, "duration_s": DISTURBANCE_EPISODE_S,
        "scored_from_s": DISTURBANCE_AT_S + SETTLE_S, "family": family,
        "verdict": _disturbance_verdict, "plant_factory": plant_factory, "limits": limits,
    }
    episodes, audit = _run_suite(factory, **common)
    aggregate = _base_aggregate(episodes)
    pdm = {str(e.index): post_disturbance_mae(e.trace) for e in episodes}
    aggregate["median_post_disturbance_mae"] = _median(list(pdm.values()))
    n_safe = int(aggregate["n_passed"])
    gate_passed = n_safe == len(episodes)
    gate_reasons = [
        f"{n_safe}/{len(episodes)} episodes safe (zero invalid outputs, zero hard violations)",
        f"total_overrides={int(aggregate['total_overrides'])} (allowed here, counted)",
        "G3-candidate passed" if gate_passed else "G3-candidate failed",
    ]
    comparison: dict[str, Any] = {"post_disturbance_mae": pdm}
    block, prefixed, b_audit = _baseline_block("baseline_pid", PIDController, **common)
    comparison["baseline_pid"] = block
    aggregate.update(prefixed)
    audit.extend(b_audit)
    comparison["audit"] = audit
    return EvaluationReport(
        candidate_id=candidate_id,
        suite=f"disturbance:{family}",
        episodes=episodes,
        aggregate=aggregate,
        gate_name="G3-candidate",
        gate_passed=gate_passed,
        gate_reasons=gate_reasons,
        comparison=comparison,
    )


def _post_mae_by_index(report: EvaluationReport) -> dict[int, float]:
    stored = report.comparison.get("post_disturbance_mae", {}) or {}
    out: dict[int, float] = {}
    for e in report.episodes:
        v = stored.get(str(e.index), stored.get(e.index))  # type: ignore[call-overload]
        if v is None:
            v = post_disturbance_mae(e.trace)
        out[e.index] = float(v)
    return out


def compare_adaptation(frozen_v1: EvaluationReport, v2: EvaluationReport) -> dict[str, Any]:
    """Gate 3: same-seed comparison of frozen v1 and v2 disturbance reports.

    Episodes are matched by index. reduction = 1 - mae_v2 / mae_v1 (0 when mae_v1 ~ 0).
    Passes iff >= GATE3_MIN_PASS episodes have reduction >= GATE3_MIN_MAE_REDUCTION AND v2 has
    zero hard violations and zero invalid outputs in total.
    """
    for r in (frozen_v1, v2):
        if not r.suite.startswith("disturbance:"):
            raise ValueError(f"compare_adaptation needs disturbance reports, got suite={r.suite!r}")
    if frozen_v1.suite != v2.suite:
        raise ValueError(f"suite mismatch: {frozen_v1.suite!r} vs {v2.suite!r}")
    m1, m2 = _post_mae_by_index(frozen_v1), _post_mae_by_index(v2)
    common = sorted(set(m1) & set(m2))
    reasons: list[str] = []
    if set(m1) != set(m2):
        reasons.append(f"episode index mismatch: v1={sorted(m1)} v2={sorted(m2)}; compared {common}")
    per_index: list[dict[str, Any]] = []
    for i in common:
        a, b = m1[i], m2[i]
        red = 0.0 if (not math.isfinite(a) or abs(a) < _MAE_EPS or not math.isfinite(b)) else 1.0 - b / a
        per_index.append({"index": i, "mae_v1": a, "mae_v2": b, "reduction": red,
                          "improved": red >= GATE3_MIN_MAE_REDUCTION})
    n_improved = sum(1 for p in per_index if p["improved"])
    v2_hard = sum(e.metrics.hard_violations for e in v2.episodes)
    v2_invalid = sum(e.metrics.invalid_outputs for e in v2.episodes)
    ok_improve = n_improved >= GATE3_MIN_PASS
    reasons.append(
        f"{n_improved}/{len(per_index)} episodes cut post-change MAE by >= {GATE3_MIN_MAE_REDUCTION:.0%} "
        f"(need >= {GATE3_MIN_PASS})"
    )
    reasons.append(f"{v2.candidate_id.rsplit('-', 1)[-1]} hard_violations={v2_hard} (must be 0)")
    reasons.append(f"{v2.candidate_id.rsplit('-', 1)[-1]} invalid_outputs={v2_invalid} (must be 0)")
    gate_passed = ok_improve and v2_hard == 0 and v2_invalid == 0
    reasons.append("G3 passed" if gate_passed else "G3 failed")
    return {
        "gate_passed": gate_passed,
        "n_improved": n_improved,
        "per_index": per_index,
        "median_reduction": _median([p["reduction"] for p in per_index]),
        "reasons": reasons,
    }


def report_summary(report: EvaluationReport) -> str:
    """Compact markdown table, one row per episode (for docs/BENCHMARKS.md)."""
    lines = [
        (
            f"**{report.candidate_id}** · suite `{report.suite}` · {report.gate_name} "
            f"{'PASS' if report.gate_passed else 'FAIL'}"
        ),
        "",
        "| index | mae | in_band | energy | overrides | violations | passed |",
        "|---:|---:|---:|---:|---:|---:|:---:|",
    ]
    for e in report.episodes:
        m = e.metrics
        lines.append(
            f"| {e.index} | {m.mae:.4f} | {m.in_band_fraction:.3f} | {m.actuation_energy:.2f} | "
            f"{m.override_count} | {m.hard_violations} | {'yes' if e.passed else 'no'} |"
        )
    return "\n".join(lines)
