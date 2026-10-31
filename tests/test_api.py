"""Evidence-surface API against a recorded run (tests/fixtures/sample_run: a real live
muse-spark-1.3 run, copied byte-for-byte from artifacts/runs). No orchestrator runs start here."""
from __future__ import annotations

import hashlib
import io
import json
import shutil
import zipfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.api.manager import ManagerError, RunManager, StartRequest
from backend.main import create_app

FIXTURE = Path(__file__).parent / "fixtures" / "sample_run"
RUN_ID = json.loads((FIXTURE / "result.json").read_text())["run_id"]


@pytest.fixture()
def root(tmp_path: Path) -> Path:
    shutil.copytree(FIXTURE, tmp_path / RUN_ID)
    return tmp_path


def _never_build(req: StartRequest, root: Path):  # pragma: no cover - must not be reached
    raise AssertionError("tests must not start a real orchestrator")


@pytest.fixture()
def client(root: Path) -> TestClient:
    return TestClient(create_app(root=root, manager=RunManager(root, builder=_never_build), dist=None))


def test_health(client: TestClient) -> None:
    r = client.get("/health")
    assert r.status_code == 200
    body = r.json()
    for k in ("status", "sandbox_mode", "docker_available", "agent_mode_default", "model_default", "prompt_version"):
        assert k in body
    assert body["status"] == "ok"
    assert isinstance(body["docker_available"], bool)


def test_list_runs(client: TestClient) -> None:
    runs = client.get("/api/runs").json()
    assert [r["id"] for r in runs] == [RUN_ID]
    r = runs[0]
    assert r["label"] == "spark"
    assert r["model_id"] == "muse-spark-1.3"
    assert r["agent_mode"] == "live"
    assert r["stage"] == "STOPPED"
    assert r["n_candidates"] == 1
    assert r["started"] > 0


def test_get_run_and_404(client: TestClient) -> None:
    body = client.get(f"/api/runs/{RUN_ID}").json()
    stored = json.loads((FIXTURE / "result.json").read_text())
    assert body["source"] == "result.json"
    assert body["stage"] == stored["stage"]
    assert body["candidates"][0]["candidate_id"] == stored["candidates"][0]["candidate_id"]
    # 13 model_call events; result.json model_usage counts 14 attempts (1 failed attempt was retried).
    assert body["budgets"]["model_calls"] == 13
    assert body["model_usage"]["calls"] == 14
    assert abs(body["budgets"]["est_cost_usd"] - sum(
        e["cost_usd"] for e in map(json.loads, (FIXTURE / "event_log.jsonl").read_text().splitlines())
        if e["kind"] == "model_call")) < 1e-6
    assert client.get("/api/runs/nope").status_code == 404
    assert client.get("/api/runs/..%2F..%2Fetc").status_code == 404


def test_live_summary_without_result(root: Path, client: TestClient) -> None:
    (root / RUN_ID / "result.json").unlink()
    body = client.get(f"/api/runs/{RUN_ID}").json()
    assert body["source"] == "event_log"
    assert body["stage"] == "STOPPED"
    assert body["budgets"]["experiments_completed"] == 12
    assert body["candidates"][0]["status"] == "approved"


def test_events_pagination(client: TestClient) -> None:
    all_ev = client.get(f"/api/runs/{RUN_ID}/events").json()
    n = len((FIXTURE / "event_log.jsonl").read_text().splitlines())
    assert len(all_ev) == n
    assert [e["seq"] for e in all_ev] == list(range(1, n + 1))
    tail = client.get(f"/api/runs/{RUN_ID}/events", params={"after": 60}).json()
    assert [e["seq"] for e in tail] == list(range(61, n + 1))
    page = client.get(f"/api/runs/{RUN_ID}/events", params={"after": 10, "limit": 5}).json()
    assert [e["seq"] for e in page] == [11, 12, 13, 14, 15]
    assert client.get(f"/api/runs/{RUN_ID}/events", params={"after": n}).json() == []


def test_controllers_source_and_sha(client: TestClient) -> None:
    ctrls = client.get(f"/api/runs/{RUN_ID}/controllers").json()
    assert len(ctrls) == 1
    c = ctrls[0]
    raw = (FIXTURE / "controller_v1.py").read_bytes()
    assert c["source"].encode("utf-8") == raw
    assert c["sha256"] == hashlib.sha256(raw).hexdigest()
    assert c["sha256_verified"] is True
    assert c["status"] == "approved"
    assert c["model_id"] == "muse-spark-1.3"
    assert c["machine_card"] == (FIXTURE / "machine_card_v1.md").read_text()
    assert c["diff_from_parent"] is None and c["parent_id"] is None


def test_evaluations_load(client: TestClient) -> None:
    ev = client.get(f"/api/runs/{RUN_ID}/evaluations").json()
    assert [x["file"] for x in ev["heldout"]] == ["evaluation_v1.json"]
    assert [x["file"] for x in ev["disturbance"]] == ["evaluation_disturbance_v1.json"]
    assert ev["adaptation"] == []
    h = ev["heldout"][0]["data"]
    assert h["gate_name"] == "G2" and h["gate_passed"] is True
    assert "baseline_pid" in h["comparison"] and "baseline_onoff" in h["comparison"]
    assert ev["monitoring"]["degraded_at_t"] == 198.2
    assert len(ev["disturbance"][0]["data"]["episodes"][0]["trace"]["steps"]) > 0
    slim = client.get(f"/api/runs/{RUN_ID}/evaluations", params={"traces": "none"}).json()
    assert "trace" not in slim["heldout"][0]["data"]["episodes"][0]
    assert "trace" not in slim["monitoring"]


def test_ledger(client: TestClient) -> None:
    led = client.get(f"/api/runs/{RUN_ID}/ledger").json()
    assert led == json.loads((FIXTURE / "hypothesis_ledger.json").read_text())


def test_export_zip(client: TestClient) -> None:
    r = client.get(f"/api/runs/{RUN_ID}/export")
    assert r.status_code == 200
    assert r.headers["content-type"] == "application/zip"
    z = zipfile.ZipFile(io.BytesIO(r.content))
    names = set(z.namelist())
    assert f"{RUN_ID}/event_log.jsonl" in names and f"{RUN_ID}/controller_v1.py" in names
    assert z.read(f"{RUN_ID}/controller_v1.py") == (FIXTURE / "controller_v1.py").read_bytes()


def test_disturbance_409_when_not_deployable(client: TestClient) -> None:
    r = client.post(f"/api/runs/{RUN_ID}/disturbance", json={"family": "pump_derate"})
    assert r.status_code == 409
    assert "STOPPED" in r.json()["detail"]
    assert "pump_derate" not in r.text
    assert client.post(f"/api/runs/{RUN_ID}/disturbance", json={"family": "bogus"}).status_code == 422


class _FakeSession:
    def __init__(self, stage: str) -> None:
        self.stage = stage
        self.stop_requested = False


class _FakeOrch:
    def __init__(self) -> None:
        self.monitored: list[str | None] = []

    def run_discovery(self) -> None:
        pass

    def run_monitoring(self, family: str | None) -> None:
        self.monitored.append(family)


def test_manager_paths_with_fake_orchestrator(root: Path) -> None:
    orch, sess = _FakeOrch(), _FakeSession("EXPLORING")
    mgr = RunManager(root, builder=lambda req, r: (RUN_ID, sess, orch))
    app = TestClient(create_app(root=root, manager=mgr, dist=None))
    assert app.post("/api/runs", json={"label": "x", "agent_mode": "mock", "sandbox_mode": "subprocess_dev_only"}
                    ).json() == {"run_id": RUN_ID}
    mgr.get(RUN_ID).thread.join(2)
    r = app.post(f"/api/runs/{RUN_ID}/disturbance", json={"family": "extra_leak"})
    assert r.status_code == 409 and "EXPLORING" in r.json()["detail"]
    sess.stage = "DEPLOYABLE"
    r = app.post(f"/api/runs/{RUN_ID}/disturbance", json={"family": "extra_leak"})
    assert r.status_code == 200 and "extra_leak" not in r.text
    mgr.get(RUN_ID).thread.join(2)
    assert orch.monitored == ["extra_leak"]
    assert app.post("/api/runs", json={"label": "bad label!"}).status_code == 422


def test_start_409_when_busy(root: Path) -> None:
    import threading
    gate = threading.Event()

    class Blocking(_FakeOrch):
        def run_discovery(self) -> None:
            gate.wait(5)

    sess = _FakeSession("EXPLORING")
    mgr = RunManager(root, builder=lambda req, r: (RUN_ID, sess, Blocking()))
    app = TestClient(create_app(root=root, manager=mgr, dist=None))
    assert app.post("/api/runs", json={"agent_mode": "mock"}).status_code == 200
    try:
        assert app.post("/api/runs", json={"agent_mode": "mock"}).status_code == 409
        assert app.post(f"/api/runs/{RUN_ID}/stop").json()["stop_requested"] is True
        assert sess.stop_requested is True
    finally:
        gate.set()
        mgr.get(RUN_ID).thread.join(2)
    with pytest.raises(ManagerError):
        mgr.stop(RUN_ID)


def _sse_data(text: str) -> list[dict]:
    return [json.loads(line[5:].strip()) for line in text.splitlines() if line.startswith("data:")]


def test_stream_replay(client: TestClient) -> None:
    with client.stream("GET", f"/api/runs/{RUN_ID}/stream", params={"replay": 1, "speed": 1e6}) as r:
        assert r.status_code == 200
        assert r.headers["content-type"].startswith("text/event-stream")
        text = "".join(r.iter_text())
    data = _sse_data(text)
    events = [d for d in data if "seq" in d]
    assert len(events) == len((FIXTURE / "event_log.jsonl").read_text().splitlines())
    assert all(e["replay"] is True for e in events)
    assert events[0]["kind"] == "run_started"


def test_stream_replay_resumes_after_seq(client: TestClient) -> None:
    """Speed change mid-replay reconnects with after=<last seq>: the next event is emitted at once
    (no wait for the recorded gap before it; 65 -> 66 is 25.5 s in the fixture) and pacing resumes
    from its ts at the new speed. Here speed=1 and 66 -> 67 is ~2 ms, so this finishes fast."""
    import time
    t0 = time.time()
    with client.stream("GET", f"/api/runs/{RUN_ID}/stream", params={"replay": 1, "speed": 1, "after": 65}) as r:
        text = "".join(r.iter_text())
    elapsed = time.time() - t0
    events = [d for d in _sse_data(text) if "seq" in d]
    assert [e["seq"] for e in events] == [66, 67]
    assert all(e["replay"] is True and e["replay_speed"] == 1 for e in events)
    assert elapsed < 5, f"resume waited for the pre-resume gap ({elapsed:.1f}s)"


def test_stream_live_tail_closes_for_finished_run(client: TestClient) -> None:
    with client.stream("GET", f"/api/runs/{RUN_ID}/stream", params={"after": 65}) as r:
        text = "".join(r.iter_text())
    events = [d for d in _sse_data(text) if "seq" in d]
    assert [e["seq"] for e in events] == [66, 67]
    assert not any(e.get("replay") for e in events)


# ---------------------------------------------------------------------------------------------
# Protocol v1.1/v1.2 fields and the 2026-10-31 promotion rule, on a small synthetic bundle shaped
# like run spark3 (the real run is 26 MB, too large to vendor as a fixture).
SYN = "syn-20261101-000000-abcdef"


def _write_synthetic(root: Path, *, g3: bool, recorded_status: str, stage: str, reason: str) -> Path:
    d = root / SYN
    d.mkdir()
    ts = 1_800_000_000.0
    events = [
        {"kind": "run_started", "model": "muse-spark-1.3", "prompt_version": "v1.2", "prompt_hash": "d9206efcefe117cb",
         "agent_mode": "live", "sandbox_mode": "docker"},
        {"kind": "experiment_proposed", "experiment_id": "E1", "phase": "discovery", "command_u": 0.5, "duration_s": 1.0},
        {"kind": "experiment_result", "experiment_id": "E1", "phase": "discovery", "status": "completed",
         "samples": [{"t": 0.0, "y": 0.4, "target": 0.6, "u_requested": 0.5, "u_applied": 0.5, "override": False}]},
        {"kind": "ledger", "phase": "after_change", "hypotheses": [], "operator_note": "re-identify"},
        {"kind": "experiment_proposed", "experiment_id": "E2", "phase": "after_change", "command_u": 0.0, "duration_s": 1.0},
        {"kind": "experiment_result", "experiment_id": "E2", "phase": "after_change", "status": "completed",
         "samples": [{"t": 9.0, "y": 0.5, "target": 0.6, "u_requested": 0.0, "u_applied": 0.0, "override": False}]},
        {"kind": "reidentification_budget_exhausted"},
        {"kind": "candidate_registered", "candidate_id": f"{SYN}-v2", "version": 2, "parent_id": f"{SYN}-v1"},
        {"kind": "adaptation_result", "candidate_id": f"{SYN}-v2", "gate3_passed": g3, "nominal_gate_passed": False},
        {"kind": "stage", "from": "EVALUATING", "to": stage, "reason": reason},
    ]
    with (d / "event_log.jsonl").open("w") as f:
        for i, e in enumerate(events, 1):
            f.write(json.dumps({"seq": i, "ts": ts + i, "run_id": SYN, "stage": "X", **e}) + "\n")
    (d / "result.json").write_text(json.dumps({
        "run_id": SYN, "stage": stage, "model_id": "muse-spark-1.3", "agent_mode": "live", "prompt_version": "v1.2",
        "prompt_hash": "d9206efcefe117cb",
        "candidates": [{"candidate_id": f"{SYN}-v1", "version": 1, "status": "approved"},
                       {"candidate_id": f"{SYN}-v2", "version": 2, "status": recorded_status}],
        "stage_history": [{"from": "EVALUATING", "to": stage, "ts": ts + 10, "reason": reason}],
    }))
    (d / "experiments.json").write_text(json.dumps([
        {"id": "E1", "phase": "discovery", "status": "completed", "t_start": 0.0, "proposal": {"command_u": 0.5},
         "command_before": 0.0, "seconds_since_command_last_changed_at_start": 0.0, "samples": []},
        {"id": "E2", "phase": "after_change", "status": "completed", "t_start": 9.0, "proposal": {"command_u": 0.0},
         "command_before": 0.55, "seconds_since_command_last_changed_at_start": 12.0, "samples": []},
    ]))
    (d / "evaluation_v2.json").write_text(json.dumps({"candidate_id": f"{SYN}-v2", "suite": "heldout",
                                                      "gate_name": "G2", "gate_passed": False, "episodes": []}))
    (d / "adaptation_v2.json").write_text(json.dumps({
        "comparison": {"gate_passed": g3, "n_improved": 5, "median_reduction": 0.77, "per_index": [],
                       "reasons": ["5/5 episodes cut post-change MAE by >= 20% (need >= 3)",
                                   "G3 passed" if g3 else "G3 failed"]},
        "nominal_gate": False, "diagnosis_category": "response_slower", "diagnosis_correct": True}))
    return d


def test_repair_verdict_disagreement_is_explained_not_rewritten(tmp_path: Path) -> None:
    reason = "adaptation attempts exhausted; last approved controller retained"
    _write_synthetic(tmp_path, g3=True, recorded_status="failed_gate", stage="FAILED", reason=reason)
    app = TestClient(create_app(root=tmp_path, manager=RunManager(tmp_path, builder=_never_build), dist=None))
    ev = app.get(f"/api/runs/{SYN}/evaluations").json()
    assert ev["protocol"] == {"prompt_version": "v1.2", "prompt_hash": "d9206efcefe117cb"}
    [v] = ev["repair_verdicts"]
    assert v["gate3_passed"] is True
    assert v["nominal_after_repair_passed"] is False and v["nominal_after_repair_gated"] is False
    assert v["recorded_candidate_status"] == "failed_gate"
    assert v["recorded_outcome"] == {"stage": "FAILED", "reason": reason, "source": "result.json", "final": True}
    assert v["verdict_disagrees"] is True
    assert v["note"] == (f"Recorded verdict under the promotion rule in force at run time: {reason}. "
                         "Under the current rule this candidate meets Gate 3.")
    run = app.get(f"/api/runs/{SYN}").json()
    assert run["stage"] == "FAILED" and run["prompt_version"] == "v1.2"  # recorded verdict untouched
    assert run["recorded_outcome"]["reason"] == reason


def test_repair_verdict_agreement_has_no_note(tmp_path: Path) -> None:
    _write_synthetic(tmp_path, g3=False, recorded_status="failed_gate", stage="FAILED", reason="x")
    app = TestClient(create_app(root=tmp_path, manager=RunManager(tmp_path, builder=_never_build), dist=None))
    [v] = app.get(f"/api/runs/{SYN}/evaluations").json()["repair_verdicts"]
    assert v["gate3_passed"] is False and v["verdict_disagrees"] is False and v["note"] is None


def test_experiment_phase_and_trusted_facts(tmp_path: Path, client: TestClient) -> None:
    _write_synthetic(tmp_path, g3=True, recorded_status="failed_gate", stage="FAILED", reason="x")
    app = TestClient(create_app(root=tmp_path, manager=RunManager(tmp_path, builder=_never_build), dist=None))
    exps = app.get(f"/api/runs/{SYN}/experiments").json()
    assert [(e["id"], e["phase"]) for e in exps] == [("E1", "discovery"), ("E2", "after_change")]
    assert exps[1]["command_before"] == 0.55 and exps[1]["seconds_since_command_last_changed_at_start"] == 12.0
    evs = app.get(f"/api/runs/{SYN}/events").json()
    assert [e["phase"] for e in evs if e["kind"] == "experiment_result"] == ["discovery", "after_change"]
    assert any(e["kind"] == "reidentification_budget_exhausted" for e in evs)
    # Older runs (v1.0 fixture): phase defaults to discovery, facts absent, no repair verdicts.
    old = client.get(f"/api/runs/{RUN_ID}/experiments").json()
    assert len(old) == 12 and {e["phase"] for e in old} == {"discovery"}
    assert all(e["command_before"] is None for e in old)
    ev_old = client.get(f"/api/runs/{RUN_ID}/evaluations", params={"traces": "none"}).json()
    assert ev_old["repair_verdicts"] == [] and ev_old["protocol"]["prompt_version"] == "v1.0"
