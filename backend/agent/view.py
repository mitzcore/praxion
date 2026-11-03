"""The agent view: the ONLY path from trusted session state to the model.

Everything Muse is permitted to know is assembled here and nowhere else. Every view sent to the
model is snapshotted to the run's artifact directory so real runs can be audited after the fact
by ``tests/test_agent_blindness.py`` and by judges.

Forbidden in a view: hidden parameter names or values, simulator truth (h_true), evaluation
seeds, disturbance family names or mechanisms, baseline controller names or source, and the
contents of Trace.meta.
"""
from __future__ import annotations

import json
import re
from typing import Any

from backend.agent.session import CandidateRecord, ExperimentRecord, Session

# Layer 1: keys produced by trusted code that must never be present anywhere in a view.
FORBIDDEN_KEYS: frozenset[str] = frozenset({
    "h_true", "hidden_params", "seed", "plant_seed", "scenario", "scenario_seed", "meta", "disturbance",
    "disturbance_family", "disturbance_at", "disturbance_at_t", "family", "audit", "comparison", "reason",
    "tank_area", "pump_gain", "deadband", "tau", "drain_coeff", "leak_base", "noise_std", "delay_nominal",
    "tau_factor", "delay_s", "h0",
})
# Layer 2: specific identifiers that cannot occur legitimately in any value (model text included).
FORBIDDEN_SUBSTRINGS: tuple[str, ...] = (
    "h_true", "hidden_params", "tank_area", "pump_gain", "drain_coeff", "leak_base", "noise_std", "delay_nominal",
    "tau_factor", "pump_derate", "extra_leak", "drain_shift", "actuator_lag", "disturbance_family", "baseline_pid",
    "baseline_onoff", "slow_pid", "PIDController", "OnOffController", "SLOW_PID", "MOCK CONTROLLER",
)
# Layer 3: whole-number tokens in the evaluator-only seed ranges, scanned everywhere except model-authored
# free text (a model that never saw a seed cannot leak one; it could coincidentally write a number).
_HIDDEN_SEED_RE = re.compile(r"(?<![\d.])(?:10[01]\d|20[01]\d)(?![\d.])")
MODEL_FREE_TEXT_KEYS: frozenset[str] = frozenset({
    "statement", "operator_note", "uncertainty_targeted", "expected_observation", "safety_argument",
    "readiness_justification", "machine_card", "design_rationale", "diagnosis", "change_summary", "predicted_behavior",
})


# Candidate ids are ``<run_id>-v<N>``. The run id carries the operator's label (which may name the
# disturbance, e.g. "fan") and the plant seed; the model only ever sees the opaque version "vN".
_OPAQUE_RE = re.compile(r"-v([1-9][0-9]*)$")


def opaque_candidate_id(candidate_id: str | None) -> str | None:
    """``"<run_id>-v3"`` -> ``"v3"``. Anything else is returned unchanged."""
    if candidate_id is None:
        return None
    m = _OPAQUE_RE.search(candidate_id)
    return f"v{m.group(1)}" if m else candidate_id


def build_agent_view(session: Session, *, include_candidate_traces: bool = True) -> dict[str, Any]:
    """Assemble the permitted projection of the session for the next model call."""
    view: dict[str, Any] = {
        "plant": {
            "description": session.plant_description,
            "u_range": list(session.constraints.u_range),
            "y_range": [0.0, 1.0],
        },
        "objective": {
            "target": session.objective.target,
            "band": list(session.objective.band),
            "scored_after_settling_s": session.objective.settle_s,
            "scored_episode_s": session.objective.episode_s,
            "notes": "Maximize time in band and minimize tracking error; lower actuation energy is better at equal tracking.",
        },
        "constraints": {
            "soft_high_limit": session.constraints.soft_high_limit,
            "hard_cutoff_forces_u_to_zero_at": session.constraints.hard_cutoff,
            "max_single_experiment_s": session.constraints.max_single_experiment_s,
            "after_change_max_single_experiment_s": session.constraints.after_change_max_single_experiment_s,
            "worst_case_rate_per_unit_u_per_s": session.constraints.worst_case_rate_per_unit_u,
            "experiments_remaining": session.experiments_remaining(),
            "after_change_experiments_remaining": session.reidentification_remaining(),
            "candidates_remaining": session.candidates_remaining(),
            "min_completed_experiments_before_controller": session.budget.min_experiments_before_generate,
        },
        "current_observation": (
            {"t": round(session.current_obs.t, 2), "y": round(session.current_obs.y, 4)} if session.current_obs else None
        ),
        "experiments": [_experiment_view(e) for e in session.experiments],
        "ledger": [h.model_dump() for h in session.ledger],
        "candidates": [_candidate_view(c, include_candidate_traces) for c in session.candidates],
        "monitoring": _monitoring_view(session),
    }
    return view


def _experiment_view(e: ExperimentRecord) -> dict[str, Any]:
    p = e.proposal
    out: dict[str, Any] = {
        "id": e.id,
        "phase": e.phase,
        "status": e.status,
        "command_u": p.get("command_u"),
        "duration_s": p.get("duration_s"),
        "command_before": e.u_before,
        "seconds_since_command_last_changed_at_start": e.t_since_last_command_change_s,
        "uncertainty_targeted": p.get("uncertainty_targeted"),
        "expected_observation": p.get("expected_observation"),
        "verdict": e.verdict.reason,
    }
    if e.trace is not None:
        out["t_start"] = e.t_start
        out["samples"] = [[s["t"], s["y"]] for s in e.trace.agent_safe(60)]
        out["measured_summary"] = e.trace.measured_summary(tail_s=5.0)
        out["any_override"] = any(s["override"] for s in e.trace.agent_safe(60))
    return out


def _candidate_view(c: CandidateRecord, include_traces: bool) -> dict[str, Any]:
    out: dict[str, Any] = {
        "candidate_id": opaque_candidate_id(c.candidate_id),
        "version": c.version,
        "parent_id": opaque_candidate_id(c.parent_id),
        "status": c.status,
        "static_check": {"ok": c.static_ok, "violations": c.static_violations},
        "sandbox_check": {"ok": c.sandbox_ok, "detail": c.sandbox_detail},
    }
    if c.evaluation is not None:
        out["evaluation"] = c.evaluation.agent_safe(include_traces=include_traces)
    if c.disturbance_evaluation is not None:
        out["post_change_evaluation"] = c.disturbance_evaluation.agent_safe(include_traces=include_traces)
    return out


def _monitoring_view(session: Session) -> dict[str, Any] | None:
    m = session.monitoring
    if m.deployed_candidate_id is None:
        return None
    out: dict[str, Any] = {
        "deployed_candidate_id": opaque_candidate_id(m.deployed_candidate_id),
        "degraded": m.degraded,
        "baseline_window_mae": _r(m.baseline_window_mae),
        "recent_window_mae": _r(m.recent_window_mae),
    }
    if m.pre_trace is not None:
        out["before_change_trace"] = m.pre_trace.agent_safe(120)
    if m.post_trace is not None:
        out["after_change_trace"] = m.post_trace.agent_safe(120)
    return out


def _r(x: float | None) -> float | None:
    return None if x is None else round(x, 4)


def serialize_view(view: dict[str, Any]) -> str:
    return json.dumps(view, indent=1, sort_keys=True)


def _walk(node: Any, path: str, out: list[str], free_text: list[str]) -> None:
    if isinstance(node, dict):
        for k, v in node.items():
            if k in FORBIDDEN_KEYS:
                out.append(f"forbidden key {k!r} at {path or '$'}")
            if k in MODEL_FREE_TEXT_KEYS and isinstance(v, str):
                free_text.append(v)
                continue
            _walk(v, f"{path}.{k}" if path else k, out, free_text)
    elif isinstance(node, list):
        for i, v in enumerate(node):
            _walk(v, f"{path}[{i}]", out, free_text)


def find_leaks(view: dict[str, Any] | str, *, secrets: tuple[str, ...] = ()) -> list[str]:
    """Return a list of leak descriptions found in a view (empty means clean).

    Keys are checked structurally (trusted code names them). Values are checked for specific
    trusted-only identifiers everywhere, and for hidden-seed-like numbers everywhere except
    model-authored free text. ``secrets`` are run-specific strings that must not appear anywhere
    (the run id, which carries the operator's label and the plant seed)."""
    data = json.loads(view) if isinstance(view, str) else view
    leaks: list[str] = []
    free_text: list[str] = []
    _walk(data, "", leaks, free_text)
    full = serialize_view(data)
    low = full.lower()
    leaks += [f"forbidden substring {s!r}" for s in FORBIDDEN_SUBSTRINGS if s.lower() in low]
    leaks += [f"run-specific secret {s!r}" for s in secrets if len(s) >= 4 and s.lower() in low]
    structural = full
    for t in free_text:
        structural = structural.replace(json.dumps(t), '""')
    for m in _HIDDEN_SEED_RE.finditer(structural):
        leaks.append(f"hidden-seed-like token {m.group(0)!r} at offset {m.start()}")
    return leaks


def assert_blind(view: dict[str, Any] | str) -> None:
    leaks = find_leaks(view)
    if leaks:
        raise AssertionError("agent view leaks trusted data: " + "; ".join(leaks))
