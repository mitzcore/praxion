"""Evaluation report schemas (trusted) and their agent-safe projection.

An EvaluationReport is produced by the evaluator (evaluation/suite.py). It contains trusted data
(traces with h_true, seeds, disturbance families). The ONLY way it reaches the agent is through
``agent_safe()``, which keeps scores and downsampled measured traces and drops everything else.
Scores on hidden episodes are the agent's test feedback, like a CI report; the seeds, the
hidden mechanism, and the true state are not.
"""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from backend.schemas import Metrics, Trace


def _opaque(candidate_id: str) -> str:
    """``"<run_id>-v3"`` -> ``"v3"`` (mirrors backend.agent.view.opaque_candidate_id without the import)."""
    _head, sep, tail = candidate_id.rpartition("-v")
    return f"v{tail}" if sep and tail.isdigit() else candidate_id


class EpisodeResult(BaseModel):
    index: int = Field(description="Position in the suite, NOT the seed.")
    seed: int = Field(description="TRUSTED ONLY.")
    disturbance_family: str | None = Field(default=None, description="TRUSTED ONLY.")
    metrics: Metrics
    trace: Trace
    passed: bool
    fail_reasons: list[str] = Field(default_factory=list)


class EvaluationReport(BaseModel):
    candidate_id: str
    suite: str = Field(description="'heldout' | 'disturbance:<family>' | 'nominal_monitor'")
    episodes: list[EpisodeResult]
    aggregate: dict[str, float] = Field(default_factory=dict)
    gate_name: str = ""
    gate_passed: bool = False
    gate_reasons: list[str] = Field(default_factory=list)
    comparison: dict[str, Any] = Field(default_factory=dict, description="vs parent / baselines; trusted.")

    def agent_safe(self, max_trace_points: int = 150, include_traces: bool = True,
                   band: tuple[float, float] = (0.55, 0.65)) -> dict[str, Any]:
        """Scores plus measured (noisy) traces only. No seeds, families, truth, or baseline names."""
        eps = []
        for e in self.episodes:
            m = e.metrics
            item: dict[str, Any] = {
                "index": e.index,
                "passed": e.passed,
                "fail_reasons": list(e.fail_reasons),
                "mae": round(m.mae, 4),
                "in_band_fraction": round(m.in_band_fraction, 3),
                "actuation_energy": round(m.actuation_energy, 3),
                "override_count": m.override_count,
                "invalid_outputs": m.invalid_outputs,
                "hard_violations": m.hard_violations,
            }
            item["measured_summary"] = e.trace.measured_summary(tail_s=30.0, band=band)
            if include_traces:
                item["trace"] = e.trace.agent_safe(max_trace_points)
            eps.append(item)
        agg = {k: round(v, 4) for k, v in self.aggregate.items() if not k.startswith("baseline")}
        return {
            # Opaque to the agent: the run id inside a candidate id carries the operator's label and plant seed.
            "candidate_id": _opaque(self.candidate_id),
            "suite_kind": "disturbance" if self.suite.startswith("disturbance") else self.suite,
            "gate_passed": self.gate_passed,
            "gate_reasons": [r.replace(self.candidate_id, _opaque(self.candidate_id)) for r in self.gate_reasons],
            "aggregate": agg,
            "episodes": eps,
        }
