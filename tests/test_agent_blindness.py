"""The agent view must never leak trusted data. Unit-level here; real-run audit in scripts/audit_run.py."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from backend.agent.contracts import Hypothesis
from backend.agent.session import CandidateRecord, ExperimentRecord, MonitoringState, Session
from backend.agent.view import build_agent_view, find_leaks, serialize_view
from backend.controller.runtime import run_constant_input, run_episode
from backend.evaluation.baselines import PIDController
from backend.evaluation.config import SETTLE_S
from backend.evaluation.metrics import compute_metrics
from backend.evaluation.report import EpisodeResult, EvaluationReport
from backend.plant.tank_sim import TankSimulator
from backend.safety.supervisor import Supervisor
from backend.schemas import DisturbanceSpec, ProposalVerdict


def _rich_session() -> Session:
    plant, sup = TankSimulator(), Supervisor()
    s = Session(run_id="t-run", plant_description=plant.public_description(), model_id="muse-spark-1.3")
    plant.reset(1007)
    s.current_obs = plant.observe()
    # experiments with trusted traces (h_true present in trace, must not appear in view)
    for i, u in enumerate([0.4, 0.7, 0.0]):
        tr = run_constant_input(plant, sup, u, 8.0, 0.6)
        s.experiments.append(ExperimentRecord(
            id=f"E{i+1}", proposal={"command_u": u, "duration_s": 8.0, "uncertainty_targeted": "gain", "expected_observation": "rise"},
            verdict=ProposalVerdict(ok=True, reason="approved; worst-case bound 0.6", u=u, duration_s=8.0),
            status="completed", t_start=tr.steps[0].t, trace=tr))
    s.record_ledger([Hypothesis(id="H1", statement="u raises y", confidence=0.9, evidence_refs=["E1"])], "E3")
    # candidate with evaluation on hidden seeds and a disturbance family
    eps = []
    for idx, seed in enumerate([1000, 1001]):
        tr = run_episode(TankSimulator(), PIDController(), Supervisor(), 60.0, 0.6, seed,
                         disturbance=DisturbanceSpec(family="pump_derate", at_t=30.0))
        eps.append(EpisodeResult(index=idx, seed=seed, disturbance_family="pump_derate",
                                 metrics=compute_metrics(tr, SETTLE_S), trace=tr, passed=True))
    rep = EvaluationReport(candidate_id="t-run-v1", suite="disturbance:pump_derate", episodes=eps,
                           aggregate={"median_mae": 0.01, "baseline_pid_median_mae": 0.009}, gate_passed=True,
                           comparison={"baseline_pid": {"mae": 0.009}, "seeds": [1000, 1001]})
    s.candidates.append(CandidateRecord(candidate_id="t-run-v1", version=1, parent_id=None, model_id="muse-spark-1.3",
                                        prompt_hash="abc", submission_kind="controller",
                                        submission={"source_code": "def control(obs, state): return 0.5, state"},
                                        static_ok=True, sandbox_ok=True, evaluation=rep, status="approved"))
    s.monitoring = MonitoringState(deployed_candidate_id="t-run-v1", baseline_window_mae=0.01, recent_window_mae=0.08,
                                   degraded=True, degraded_at_t=75.0, pre_trace=eps[0].trace, post_trace=eps[1].trace,
                                   disturbance_family="pump_derate", disturbance_at_t=60.0)
    return s


def test_rich_view_has_no_leaks() -> None:
    view = build_agent_view(_rich_session())
    text = serialize_view(view)
    assert find_leaks(text) == [], find_leaks(text)
    # structural guarantees
    assert "h_true" not in text and "pump_derate" not in text and "1000" not in text
    assert view["experiments"][0]["samples"] and len(view["experiments"][0]["samples"][0]) == 2
    assert view["candidates"][0]["evaluation"]["episodes"][0]["trace"][0].keys() == {
        "t", "y", "target", "u_requested", "u_applied", "override"}
    assert "baseline_pid_median_mae" not in text
    assert view["monitoring"]["after_change_trace"]


def test_scanner_catches_planted_leaks() -> None:
    clean = build_agent_view(_rich_session())
    for leak in ({"x": {"h_true": 0.6}}, {"note": "seed 1003 used"}, {"m": "pump_derate at 60"}, {"s": 2004}):
        v = dict(clean)
        v["planted"] = leak
        assert find_leaks(v), f"scanner missed {leak}"


def test_scanner_tolerates_model_english() -> None:
    """Model-authored text may legitimately contain ordinary words; only trusted identifiers are leaks."""
    s = _rich_session()
    s.record_ledger([Hypothesis(id="H9", statement="There is a hidden dead zone; the seed of this idea is E2; meta-stable at 0.6",
                                confidence=0.4, evidence_refs=["E2"])], "E3")
    s.experiments[0].proposal["operator_note"] = "Probing the hidden deadband near 1005 units"
    assert find_leaks(build_agent_view(s)) == []


def test_scanner_catches_structural_keys_and_identifiers() -> None:
    assert find_leaks({"meta": {"x": 1}}) and find_leaks({"a": {"h_true": 0.5}})
    assert find_leaks({"note": "baseline_pid did better"}) and find_leaks({"n": "uses pump_derate"})
    assert find_leaks({"verdict": "approved on 1005"}) and find_leaks({"s": 2004})


def test_scanner_tolerates_ordinary_numbers() -> None:
    assert find_leaks({"t": 100.5, "y": 0.2001, "n": 10000, "x": 1000.0, "w": 999}) == []


def test_source_code_never_in_view_unless_candidate_section() -> None:
    """Source is shown to Muse only via revision prompts, not in the view (keeps views small and auditable)."""
    view = build_agent_view(_rich_session())
    assert "def control" not in serialize_view(view)


@pytest.mark.parametrize("snapshot_dir", sorted(Path("artifacts/runs").glob("*/agent_view_snapshots")) or [None])
def test_real_run_snapshots_are_blind(snapshot_dir: Path | None) -> None:
    """Audits every view actually sent to the model in any locally recorded run."""
    if snapshot_dir is None:
        pytest.skip("no recorded runs yet")
    for p in sorted(snapshot_dir.glob("*.json")):
        leaks = find_leaks(json.loads(p.read_text()))
        assert leaks == [], f"{p}: {leaks}"


def test_candidate_ids_are_opaque_and_run_id_is_a_secret() -> None:
    """The run id carries the operator's label (which may name the disturbance, e.g. "fan") and the plant
    seed. The model sees only "vN", and the scanner treats the run id as a forbidden secret."""
    s = _rich_session()
    view = build_agent_view(s)
    ids = [c["candidate_id"] for c in view["candidates"]]
    assert ids and all(i.startswith("v") and i[1:].isdigit() for i in ids), ids
    assert all(c["parent_id"] is None or c["parent_id"].startswith("v") for c in view["candidates"])
    assert s.run_id not in serialize_view(view)
    assert find_leaks(view, secrets=(s.run_id,)) == []
    planted = json.loads(serialize_view(view))
    planted["objective"]["notes"] = f"see {s.run_id}"
    assert any("secret" in leak for leak in find_leaks(planted, secrets=(s.run_id,)))


def test_opaque_candidate_id_helper() -> None:
    from backend.agent.view import opaque_candidate_id
    assert opaque_candidate_id("tclabsim-fan5-20261101-104237-bfe4bb-v2") == "v2"
    assert opaque_candidate_id("v13-s11-20261031-020922-a0e68e-v1") == "v1"
    assert opaque_candidate_id(None) is None
    assert opaque_candidate_id("odd") == "odd"


@pytest.mark.parametrize("calls_file", sorted(Path("artifacts/runs").glob("*/model_calls.jsonl")) or [None])
def test_real_run_model_calls_are_blind(calls_file: Path | None) -> None:
    """Audits the full request messages actually sent to the model, not only the view snapshots.

    Forbidden identifiers and hidden-seed tokens must never appear. The run id (operator label, plant
    seed) is checked for runs started on or after 2026-11-02; earlier runs carried it in candidate ids,
    which is recorded as a known contamination of their diagnosis-correctness scores."""
    if calls_file is None:
        pytest.skip("no recorded runs yet")
    run_id = calls_file.parent.name
    date = next((tok for tok in run_id.split("-") if len(tok) == 8 and tok.isdigit()), "0")
    secrets = (run_id,) if date >= "20261102" else ()
    for line in calls_file.read_text().splitlines():
        rec = json.loads(line)
        msgs = rec.get("request_messages") or []
        leaks = find_leaks({"messages": msgs}, secrets=secrets)
        assert leaks == [], f"{calls_file} stage={rec.get('stage')}: {leaks}"


def test_readiness_ignores_experiments_without_samples() -> None:
    from backend.agent.session import MIN_EXPERIMENT_SAMPLES
    s = _rich_session()
    _ok, _ = s.may_generate()
    n_real = len(s.completed_experiments())
    # Replace every completed experiment's trace with an empty one: nothing should count any more.
    for e in s.completed_experiments():
        e.trace = e.trace.model_copy(update={"steps": []}) if e.trace is not None else None
    if all(e.trace is not None for e in s.completed_experiments()):
        ok2, why = s.may_generate()
        assert not ok2 and "0 completed" in why, (n_real, why)
    assert MIN_EXPERIMENT_SAMPLES >= 1
