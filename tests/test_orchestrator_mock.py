"""End-to-end orchestrator run with the labeled MOCK agent. No credits, no claims: plumbing only."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from backend.agent.mock_agent import MOCK_MODEL_ID, MockMuseClient
from backend.agent.orchestrator import Orchestrator, OrchestratorConfig
from backend.agent.session import Budget, Session
from backend.agent.view import find_leaks
from backend.controller.sandbox import docker_available
from backend.plant.tank_sim import TankSimulator
from backend.safety.supervisor import Supervisor
from backend.storage.artifacts import RunStore

pytestmark = pytest.mark.slow


def _run(tmp_path: Path, sandbox_mode: str, family: str | None) -> tuple[Session, RunStore]:
    plant = TankSimulator()
    store = RunStore("mock-e2e", root=tmp_path / "runs")
    session = Session(run_id="mock-e2e", plant_description=plant.public_description(), agent_mode="mock",
                      budget=Budget(max_experiments=6, max_candidates=3))
    orch = Orchestrator(session, store, MockMuseClient(), plant, Supervisor(), None,
                        OrchestratorConfig(plant_seed=5, sandbox_mode=sandbox_mode, monitor_pre_s=60.0,
                                           monitor_post_detection_s=30.0))
    orch.run_discovery()
    if session.stage == "DEPLOYABLE":
        orch.run_monitoring(family)
    return session, store


@pytest.fixture(scope="module")
def mock_run(tmp_path_factory: pytest.TempPathFactory) -> tuple[Session, RunStore]:
    return _run(tmp_path_factory.mktemp("e2e"), "subprocess_dev_only", "actuator_lag")


def test_stage_sequence_and_artifacts(mock_run: tuple[Session, RunStore]) -> None:
    s, store = mock_run
    visited = [h["to"] for h in s.stage_history]
    assert visited[:2] == ["EXPLORING", "GENERATING"]
    assert "STATIC_CHECK" in visited and "SANDBOX_CHECK" in visited and "EVALUATING" in visited
    assert s.stage in {"COMPLETE", "FAILED", "DEPLOYABLE"}, s.stage_history[-1]
    assert len(s.completed_experiments()) >= s.budget.min_experiments_before_generate
    assert s.ledger_history and s.candidates
    for name in ("event_log.jsonl", "result.json", "experiments.json", "hypothesis_ledger.json", "controller_v1.py",
                 "evaluation_v1.json", "machine_card_v1.md"):
        assert (store.dir / name).exists(), name
    result = json.loads((store.dir / "result.json").read_text())
    assert result["model_id"] == MOCK_MODEL_ID and result["agent_mode"] == "mock"
    kinds = {e["kind"] for e in store.events()}
    assert {"run_started", "stage", "model_call", "ledger", "experiment_proposed", "experiment_result",
            "candidate_registered", "static_check", "sandbox_check", "evaluation"} <= kinds


def test_registry_bytes_match_model_output(mock_run: tuple[Session, RunStore]) -> None:
    s, store = mock_run
    for c in s.candidates:
        src = c.submission["source_code"]
        assert (store.dir / f"controller_v{c.version}.py").read_bytes() == src.encode("utf-8")


def test_every_view_snapshot_is_blind(mock_run: tuple[Session, RunStore]) -> None:
    _, store = mock_run
    snaps = store.view_snapshots()
    assert snaps, "no agent view snapshots recorded"
    for v in snaps:
        assert find_leaks(v) == []


def test_monitoring_recorded_without_leaking_family(mock_run: tuple[Session, RunStore]) -> None:
    s, store = mock_run
    if s.monitoring.deployed_candidate_id is None:
        pytest.skip("v1 did not pass the gate under mock; monitoring not reached")
    assert (store.dir / "monitoring.json").exists()
    text = json.dumps(store.view_snapshots())
    assert "actuator_lag" not in text
    sched = store.events("disturbance_scheduled")
    assert sched and "family" not in sched[0]


@pytest.mark.docker
@pytest.mark.skipif(not docker_available(), reason="docker not available")
def test_docker_mode_smoke(tmp_path: Path) -> None:
    s, _ = _run(tmp_path, "docker", None)
    assert s.candidates and s.candidates[0].sandbox_ok is not None
