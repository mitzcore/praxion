"""Gate 3 comparison logic (compare_adaptation) on hand-built reports."""
from __future__ import annotations

import pytest

from backend.evaluation.report import EpisodeResult, EvaluationReport
from backend.evaluation.suite import compare_adaptation
from backend.schemas import Metrics, Trace, TraceStep


def _trace(level: float) -> Trace:
    steps = [TraceStep(t=round(k * 0.1, 1), y=level, h_true=level, u_requested=0.5, u_applied=0.5,
                       override=False, reason="ok") for k in range(20)]
    return Trace(steps=steps, dt=0.1, target=0.6, disturbance_at=1.0)


def _report(maes: list[float], hard: list[int] | None = None, cid: str = "c") -> EvaluationReport:
    hard = hard or [0] * len(maes)
    eps = []
    for i, (m, hv) in enumerate(zip(maes, hard)):
        metrics = Metrics(mae=m, in_band_fraction=0.9, actuation_energy=1.0, override_count=0,
                          hard_violations=hv, invalid_outputs=0, steps=20, scored_steps=10)
        eps.append(EpisodeResult(index=i, seed=2000 + i, disturbance_family="pump_derate", metrics=metrics,
                                 trace=_trace(0.6 - m), passed=hv == 0))
    return EvaluationReport(candidate_id=cid, suite="disturbance:pump_derate", episodes=eps,
                            comparison={"post_disturbance_mae": {str(i): m for i, m in enumerate(maes)}})


V1 = [0.10, 0.10, 0.10, 0.10, 0.10]


def test_gate3_passes_when_4_of_5_improve_30pct():
    v2 = [0.07, 0.07, 0.07, 0.07, 0.10]
    out = compare_adaptation(_report(V1), _report(v2))
    assert out["gate_passed"] is True
    assert out["n_improved"] == 4
    assert out["per_index"][0]["reduction"] == pytest.approx(0.30)
    assert out["per_index"][4]["reduction"] == pytest.approx(0.0)
    assert out["median_reduction"] == pytest.approx(0.30)


def test_gate3_fails_on_hard_violation():
    v2 = [0.07, 0.07, 0.07, 0.07, 0.10]
    out = compare_adaptation(_report(V1), _report(v2, hard=[0, 0, 1, 0, 0]))
    assert out["gate_passed"] is False
    assert out["n_improved"] == 4
    assert any("hard_violations=1" in r for r in out["reasons"])


def test_gate3_fails_when_only_2_improve():
    v2 = [0.07, 0.07, 0.09, 0.10, 0.12]
    out = compare_adaptation(_report(V1), _report(v2))
    assert out["gate_passed"] is False
    assert out["n_improved"] == 2


def test_zero_v1_mae_guard():
    out = compare_adaptation(_report([0.0] * 5), _report([0.05] * 5))
    assert all(p["reduction"] == 0.0 for p in out["per_index"])
    assert out["gate_passed"] is False


def test_falls_back_to_trace_when_comparison_missing():
    r1, r2 = _report(V1), _report([0.05] * 5)
    r1.comparison = {}
    out = compare_adaptation(r1, r2)
    assert out["per_index"][0]["mae_v1"] == pytest.approx(0.10)
    assert out["gate_passed"] is True


def test_rejects_mismatched_suites():
    r2 = _report(V1)
    r2.suite = "disturbance:extra_leak"
    with pytest.raises(ValueError):
        compare_adaptation(_report(V1), r2)
    r3 = _report(V1)
    r3.suite = "heldout"
    with pytest.raises(ValueError):
        compare_adaptation(r3, r3)


def test_roundtrip_report_still_compares():
    r1 = EvaluationReport.model_validate_json(_report(V1).model_dump_json())
    out = compare_adaptation(r1, _report([0.07] * 5))
    assert out["n_improved"] == 5
