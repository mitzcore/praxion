"""scripts/audit_run.py: a clean synthetic bundle passes; tampering is caught."""
from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
import time
from pathlib import Path
from typing import Any

from backend.controller.registry import Registry

ROOT = Path(__file__).resolve().parents[1]
BENIGN = ROOT / "tests" / "benign_candidates"
FIXTURE_MODEL = "MOCK-NOT-MUSE"  # synthetic fixture: never labeled as Muse output


def _load(name: str):
    spec = importlib.util.spec_from_file_location(f"praxion_{name}", ROOT / "scripts" / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
    sys.modules[spec.name] = mod  # dataclasses resolve annotations through sys.modules
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


audit_run = _load("audit_run")


def build_run(artifact_root: Path, run_id: str = "synth-20261031-000000-abcdef",
              sources: tuple[str, ...] = ("pi_controller.py",), statuses: tuple[str, ...] = ("approved",),
              family: str | None = "actuator_lag") -> Path:
    """Hand-built MOCK bundle in the RunStore layout: registry candidates, events, calls, snapshot, result."""
    reg = Registry(artifact_root)
    run_dir = reg.run_dir(run_id)
    (run_dir / "agent_view_snapshots").mkdir(parents=True, exist_ok=True)
    t0 = time.time()
    events: list[dict[str, Any]] = []
    stage_history: list[dict[str, Any]] = []
    calls: list[dict[str, Any]] = []
    state = {"stage": "NEW", "ts": t0}

    def ev(kind: str, **payload: Any) -> dict[str, Any]:
        state["ts"] += 1.0
        rec = {"seq": len(events) + 1, "ts": state["ts"], "run_id": run_id, "kind": kind, "stage": state["stage"],
               **payload}
        events.append(rec)
        return rec

    def stage(to: str, **info: Any) -> None:
        rec = {"from": state["stage"], "to": to, "ts": state["ts"] + 1.0, **info}
        stage_history.append(rec)
        state["stage"] = to
        ev("stage", **rec)

    def call(stage_name: str, body: dict[str, Any]) -> None:
        calls.append({"stage": stage_name, "model": FIXTURE_MODEL, "attempt": 1, "ok": True, "latency_s": 0.1,
                      "prompt_tokens": 10, "completion_tokens": 20, "reasoning_tokens": 5, "cached_tokens": 0,
                      "cost_usd": 0.001, "error": None,
                      "request_messages": [{"role": "system", "content": "You control an unknown tank."},
                                           {"role": "user", "content": "Propose the next step."}],
                      "response_text": json.dumps(body), "ts": state["ts"]})
        ev("model_call", call_stage=stage_name, model=FIXTURE_MODEL, ok=True)

    ev("run_started", model=FIXTURE_MODEL, prompt_version="test", agent_mode="mock")
    stage("EXPLORING")
    experiments = []
    for i, u in enumerate((0.3, 0.5, 0.7), start=1):
        call("exploring", {"command_u": u, "duration_s": 10.0})
        ev("experiment_proposed", experiment_id=f"E{i}", command_u=u)
        ev("experiment_result", experiment_id=f"E{i}", status="completed")
        experiments.append({"id": f"E{i}", "status": "completed",
                            "proposal": {"command_u": u, "duration_s": 10.0, "uncertainty_targeted": f"gain near u={u}"}})
    stage("GENERATING")
    snap = {"plant": {"description": "A tank with one pump."}, "objective": {"target": 0.6}, "ledger": []}
    (run_dir / "agent_view_snapshots" / "001_authoring.json").write_text(json.dumps(snap))
    cands = []
    parent = None
    for k, (fname, status) in enumerate(zip(sources, statuses)):
        src = (BENIGN / fname).read_text()
        call("authoring" if k == 0 else "adapting", {"source_code": src, "machine_card": "m", "design_rationale": "r"})
        c = reg.persist(src, run_id=run_id, parent_id=parent, model_id=FIXTURE_MODEL, prompt_hash="testhash",
                        rationale="r")
        ev("candidate_registered", candidate_id=c.id, version=c.version, parent_id=c.parent_id, sha256=c.sha256,
           byte_length=c.byte_length, submission_kind="controller" if k == 0 else "revision")
        stage("STATIC_CHECK", candidate_id=c.id)
        stage("SANDBOX_CHECK", candidate_id=c.id)
        stage("EVALUATING", candidate_id=c.id)
        if k == 0:
            ev("candidate_approved", candidate_id=c.id)
            stage("DEPLOYABLE", candidate_id=c.id)
            if len(sources) > 1:
                stage("MONITORING", candidate_id=c.id)
        cands.append({"candidate_id": c.id, "version": c.version, "parent_id": c.parent_id, "model_id": FIXTURE_MODEL,
                      "prompt_hash": "testhash", "submission_kind": "controller" if k == 0 else "revision",
                      "submission": {"source_code": src}, "static_ok": True, "sandbox_ok": True, "status": status})
        parent = c.id
        if k + 1 < len(sources):
            stage("ADAPTING", attempt=k + 1, parent=c.id)
    if len(sources) > 1:
        stage("FAILED", reason="adaptation attempts exhausted; last approved controller retained")
        (run_dir / f"adaptation_v{len(sources)}.json").write_text(json.dumps(
            {"comparison": {}, "nominal_gate": True, "diagnosis_category": "unknown", "diagnosis_correct": False}))

    (run_dir / "event_log.jsonl").write_text("".join(json.dumps(e) + "\n" for e in events))
    (run_dir / "model_calls.jsonl").write_text("".join(json.dumps(c) + "\n" for c in calls))
    usage = {"calls": len(calls), "failed_calls": 0, "prompt_tokens": 10 * len(calls),
             "completion_tokens": 20 * len(calls), "reasoning_tokens": 5 * len(calls), "cost_usd": 0.001 * len(calls)}
    result = {"run_id": run_id, "stage": state["stage"], "model_id": FIXTURE_MODEL, "agent_mode": "mock",
              "prompt_version": "test", "prompt_hash": "testhash", "sandbox_mode": "subprocess_dev_only",
              "experiments": experiments, "candidates": cands,
              "monitoring": {"deployed_candidate_id": cands[0]["candidate_id"], "disturbance_family": family},
              "stage_history": stage_history, "model_usage": usage, "elapsed_s": 12.0, "finished_at": state["ts"]}
    (run_dir / "result.json").write_text(json.dumps(result))
    return run_dir


def _statuses(run_dir: Path) -> dict[int, str]:
    return {c.number: c.status for c in audit_run.audit(run_dir)}


def test_clean_synthetic_run_passes(tmp_path: Path, capsys) -> None:
    run_dir = build_run(tmp_path)
    st = _statuses(run_dir)
    assert st == {1: "PASS", 2: "PASS", 3: "WARN", 4: "PASS", 5: "PASS", 6: "PASS", 7: "PASS", 8: "PASS"}  # 3: MOCK flagged; 8: skipped
    assert audit_run.main([run_dir.name, "--root", str(run_dir.parent)]) == 0
    out = capsys.readouterr().out
    assert "RESULT: PASS" in out and "MOCK" in out


def test_corrupted_controller_fails_hash(tmp_path: Path, capsys) -> None:
    run_dir = build_run(tmp_path)
    p = run_dir / "controller_v1.py"
    p.write_bytes(p.read_bytes() + b"\n# tampered\n")
    st = _statuses(run_dir)
    assert st[1] == "FAIL" and st[5] == "FAIL" and st[6] == "FAIL"
    assert audit_run.main([run_dir.name, "--root", str(run_dir.parent)]) == 1
    assert "[FAIL] 1." in capsys.readouterr().out


def test_leak_in_snapshot_fails(tmp_path: Path) -> None:
    run_dir = build_run(tmp_path)
    snap = run_dir / "agent_view_snapshots" / "001_authoring.json"
    view = json.loads(snap.read_text())
    view["operator_hint"] = "the pump_derate disturbance is coming"
    snap.write_text(json.dumps(view))
    checks = {c.number: c for c in audit_run.audit(run_dir)}
    assert checks[2].status == "FAIL"
    assert any("pump_derate" in d for d in checks[2].details)
    assert audit_run.main([run_dir.name, "--root", str(run_dir.parent)]) == 1


def test_family_name_in_request_fails(tmp_path: Path) -> None:
    run_dir = build_run(tmp_path)
    path = run_dir / "model_calls.jsonl"
    calls = [json.loads(line) for line in path.read_text().splitlines()]
    calls[0]["request_messages"][1]["content"] += " Note: actuator_lag ahead."
    path.write_text("".join(json.dumps(c) + "\n" for c in calls))
    assert _statuses(run_dir)[7] == "FAIL"


def test_illegal_transition_and_non_muse_model_fail(tmp_path: Path) -> None:
    run_dir = build_run(tmp_path)
    ev_path = run_dir / "event_log.jsonl"
    events = [json.loads(line) for line in ev_path.read_text().splitlines()]
    first_stage = next(e for e in events if e["kind"] == "stage")
    first_stage["to"] = "DEPLOYABLE"  # NEW -> DEPLOYABLE skips discovery and evaluation
    ev_path.write_text("".join(json.dumps(e) + "\n" for e in events))
    path = run_dir / "model_calls.jsonl"
    calls = [json.loads(line) for line in path.read_text().splitlines()]
    calls[0]["model"] = "gpt-4o"
    path.write_text("".join(json.dumps(c) + "\n" for c in calls))
    st = _statuses(run_dir)
    assert st[4] == "FAIL" and st[3] == "FAIL"


def test_authorship_mismatch_fails(tmp_path: Path) -> None:
    run_dir = build_run(tmp_path)
    path = run_dir / "model_calls.jsonl"
    calls = [json.loads(line) for line in path.read_text().splitlines()]
    body = json.loads(calls[-1]["response_text"])
    body["source_code"] = body["source_code"].replace("KP = 1.5", "KP = 1.6")  # trusted code "retuned" the model output
    calls[-1]["response_text"] = json.dumps(body)
    path.write_text("".join(json.dumps(c) + "\n" for c in calls))
    assert _statuses(run_dir)[6] == "FAIL"
    assert hashlib.sha256((run_dir / "controller_v1.py").read_bytes()).hexdigest()  # file itself untouched


def test_export_zip_contains_run_and_audit(tmp_path: Path) -> None:
    import zipfile

    export_artifacts = _load("export_artifacts")
    run_dir = build_run(tmp_path / "art")
    md = tmp_path / "BENCHMARKS.md"
    md.write_text("# bench\n")
    out, ok = export_artifacts.export(run_dir.name, runs_root=run_dir.parent, out=tmp_path / "x.zip",
                                      benchmarks_md=md, benchmarks_json=tmp_path / "missing.json")
    assert ok
    names = zipfile.ZipFile(out).namelist()
    assert f"runs/{run_dir.name}/controller_v1.py" in names
    assert {"AUDIT.txt", "docs/BENCHMARKS.md", "MANIFEST.json"} <= set(names)
