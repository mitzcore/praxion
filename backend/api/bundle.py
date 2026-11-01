"""Read-only access to run bundles under the artifact root.

Everything here is derived from files the orchestrator wrote. Nothing is computed that is not
directly traceable to a stored artifact (summaries are counts and sums over the event log).
"""
from __future__ import annotations

import hashlib
import io
import json
import math
import re
import zipfile
from pathlib import Path
from typing import Any

TERMINAL_STAGES = {"DEPLOYABLE", "COMPLETE", "FAILED", "STOPPED"}
FINAL_STAGES = {"COMPLETE", "FAILED", "STOPPED"}
_RUN_ID_RE = re.compile(r"^[A-Za-z0-9_.-]{1,200}$")
_VERSION_RE = re.compile(r"^controller_v(\d+)\.py$")


class RunNotFound(LookupError):
    pass


def sanitize(o: Any) -> Any:
    """Replace NaN/Inf with None so the payload is strict JSON (browsers reject NaN)."""
    if isinstance(o, float):
        return o if math.isfinite(o) else None
    if isinstance(o, dict):
        return {k: sanitize(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [sanitize(v) for v in o]
    return o


def dumps(o: Any) -> str:
    return json.dumps(sanitize(o), allow_nan=False, separators=(",", ":"))


def run_dir(root: Path, run_id: str) -> Path:
    if not _RUN_ID_RE.match(run_id) or run_id in {".", ".."}:
        raise RunNotFound(run_id)
    d = (root / run_id).resolve()
    if d.parent != root.resolve() or not d.is_dir():
        raise RunNotFound(run_id)
    return d


def _read_json(p: Path) -> Any | None:
    try:
        return json.loads(p.read_text())
    except (OSError, ValueError):
        return None


def read_events(d: Path, after: int = 0) -> list[dict[str, Any]]:
    p = d / "event_log.jsonl"
    if not p.exists():
        return []
    out: list[dict[str, Any]] = []
    with p.open() as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except ValueError:  # a partially written trailing line during a live run
                continue
            if int(rec.get("seq", 0)) > after:
                out.append(rec)
    return out


def read_result(d: Path) -> dict[str, Any] | None:
    r = _read_json(d / "result.json")
    return r if isinstance(r, dict) else None


def label_of(run_id: str) -> str:
    # new_run_id(prefix) -> "<prefix>-YYYYMMDD-HHMMSS-<hex6>"
    m = re.match(r"^(.*)-\d{8}-\d{6}-[0-9a-f]{6}$", run_id)
    return m.group(1) if m else run_id


def live_summary(d: Path, events: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    """Summary built only from the event log (used while a run has no result.json yet, and to
    supplement result.json with fields it does not carry)."""
    events = read_events(d) if events is None else events
    started = next((e for e in events if e.get("kind") == "run_started"), None)
    stage = "NEW"
    stage_history = []
    candidates: dict[str, dict[str, Any]] = {}
    n_exp_proposed = n_exp_completed = 0
    calls = failed_calls = 0
    cost = 0.0
    tokens = {"prompt_tokens": 0, "completion_tokens": 0, "reasoning_tokens": 0}
    for e in events:
        k = e.get("kind")
        if k == "stage":
            stage = e.get("to", stage)
            stage_history.append({"from": e.get("from"), "to": e.get("to"), "ts": e.get("ts"),
                                  **({"reason": e["reason"]} if "reason" in e else {})})
        elif k == "experiment_proposed":
            n_exp_proposed += 1
        elif k == "experiment_result" and e.get("status") == "completed":
            n_exp_completed += 1
        elif k == "model_call":
            calls += 1
            failed_calls += 0 if e.get("ok", True) else 1
            cost += float(e.get("cost_usd") or 0.0)
            for t in tokens:
                tokens[t] += int(e.get(t) or 0)
        elif k == "candidate_registered":
            cid = e.get("candidate_id")
            candidates[cid] = {"candidate_id": cid, "version": e.get("version"), "parent_id": e.get("parent_id"),
                               "sha256": e.get("sha256"), "submission_kind": e.get("submission_kind"),
                               "status": "registered"}
        elif k == "static_check" and e.get("candidate_id") in candidates:
            c = candidates[e["candidate_id"]]
            c["static_ok"], c["static_violations"] = bool(e.get("ok")), e.get("violations") or []
            if not e.get("ok"):
                c["status"] = "rejected_static"
        elif k == "sandbox_check" and e.get("candidate_id") in candidates:
            c = candidates[e["candidate_id"]]
            c["sandbox_ok"], c["sandbox_detail"] = bool(e.get("ok")), e.get("detail") or []
            if not e.get("ok"):
                c["status"] = "rejected_sandbox"
        elif k == "evaluation" and e.get("candidate_id") in candidates and e.get("suite") == "heldout":
            candidates[e["candidate_id"]]["status"] = "evaluated"
        elif k == "adaptation_result" and e.get("candidate_id") in candidates:
            ok = bool(e.get("gate3_passed")) and bool(e.get("nominal_gate_passed"))
            candidates[e["candidate_id"]]["status"] = "approved" if ok else "failed_gate"
        elif k == "candidate_approved" and e.get("candidate_id") in candidates:
            candidates[e["candidate_id"]]["status"] = "approved"
        elif k == "candidate_failed_gate" and e.get("candidate_id") in candidates:
            candidates[e["candidate_id"]]["status"] = "failed_gate"
    first_ts = events[0]["ts"] if events else None
    last_ts = events[-1]["ts"] if events else None
    return {
        "run_id": d.name,
        "source": "event_log",
        "stage": stage,
        "model_id": started.get("model") if started else None,
        "agent_mode": started.get("agent_mode") if started else None,
        "prompt_version": started.get("prompt_version") if started else None,
        "prompt_hash": started.get("prompt_hash") if started else None,
        "sandbox_mode": started.get("sandbox_mode") if started else None,
        "started_at": first_ts,
        "last_event_at": last_ts,
        "n_events": len(events),
        "stage_history": stage_history,
        "candidates": list(candidates.values()),
        "budgets": {"experiments_proposed": n_exp_proposed, "experiments_completed": n_exp_completed,
                    "model_calls": calls, "failed_model_calls": failed_calls, "est_cost_usd": round(cost, 6),
                    **tokens},
    }


def run_listing(d: Path) -> dict[str, Any]:
    events = read_events(d)
    live = live_summary(d, events)
    res = read_result(d)
    # result.json is written at the end of each phase; the event log is newer while a phase runs.
    stage = live["stage"] if events else (res or {}).get("stage", "NEW")
    return {
        "id": d.name,
        "label": label_of(d.name),
        "stage": stage,
        "model_id": (res or {}).get("model_id") or live["model_id"],
        "agent_mode": (res or {}).get("agent_mode") or live["agent_mode"],
        "started": live["started_at"],
        "last_event_at": live["last_event_at"],
        "n_candidates": len((res or {}).get("candidates") or live["candidates"]),
        "has_result": res is not None,
    }


def list_runs(root: Path) -> list[dict[str, Any]]:
    if not root.is_dir():
        return []
    runs = []
    for d in root.iterdir():
        if d.is_dir() and _RUN_ID_RE.match(d.name) and ((d / "event_log.jsonl").exists() or (d / "result.json").exists()):
            runs.append(run_listing(d))
    runs.sort(key=lambda r: r["started"] or 0, reverse=True)
    return runs


def get_run(d: Path) -> dict[str, Any]:
    live = live_summary(d)
    res = read_result(d)
    if res is None:
        live["display_profile"] = display_profile(d)
        return live
    out = dict(res)
    out["source"] = "result.json"
    # The event log is authoritative for the current stage if a later phase is running.
    out["stage_from_events"] = live["stage"]
    out["started_at"] = live["started_at"]
    out["last_event_at"] = live["last_event_at"]
    out["n_events"] = live["n_events"]
    out["budgets"] = live["budgets"]
    out["recorded_outcome"] = recorded_outcome(d)
    out["display_profile"] = display_profile(d)
    return out


def _sha256(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def controllers(d: Path) -> list[dict[str, Any]]:
    res = read_result(d) or {}
    summary = live_summary(d)
    live = {c["candidate_id"]: c for c in summary["candidates"]}
    # result.json is written at the end of each phase; while a later phase runs the event log is newer.
    result_current = bool(res) and res.get("stage") == summary["stage"]
    status_by_id = {c.get("candidate_id"): c for c in res.get("candidates") or []} if result_current else live
    out = []
    files = sorted((int(m.group(1)), p) for p in d.glob("controller_v*.py") if (m := _VERSION_RE.match(p.name)))
    meta_by_version = {}
    for v, p in files:
        meta_by_version[v] = _read_json(d / f"controller_v{v}.meta.json") or {}
    for v, p in files:
        meta = meta_by_version[v]
        cid = meta.get("id") or f"{d.name}-v{v}"
        parent_id = meta.get("parent_id")
        parent_version = next((pv for pv, pm in meta_by_version.items() if pm.get("id") == parent_id), None)
        if parent_version is None and parent_id:
            m = re.search(r"-v(\d+)$", parent_id)
            parent_version = int(m.group(1)) if m else None
        diff_path = d / f"controller_diff_v{parent_version}_v{v}.patch" if parent_version is not None else None
        card = d / f"machine_card_v{v}.md"
        rc = status_by_id.get(cid, {})
        sha_file = _sha256(p)
        extra = meta.get("extra") or {}
        out.append({
            "version": v,
            "candidate_id": cid,
            "sha256": sha_file,
            "sha256_recorded": meta.get("sha256"),
            "sha256_verified": meta.get("sha256") == sha_file,
            "byte_length": p.stat().st_size,
            "parent_id": parent_id,
            "parent_version": parent_version,
            "model_id": meta.get("model_id"),
            "prompt_hash": meta.get("prompt_hash"),
            "created_at": meta.get("created_at"),
            "status": rc.get("status") or live.get(cid, {}).get("status"),
            "status_source": "result.json" if result_current else "event_log",
            "submission_kind": rc.get("submission_kind") or extra.get("kind"),
            "static_ok": rc.get("static_ok"),
            "static_violations": rc.get("static_violations"),
            "sandbox_ok": rc.get("sandbox_ok"),
            "sandbox_detail": rc.get("sandbox_detail"),
            "rationale": meta.get("rationale"),
            "predicted_behavior": extra.get("predicted_behavior"),
            "diagnosis": extra.get("diagnosis"),
            "diagnosis_category": extra.get("diagnosis_category"),
            "source": p.read_text(),
            "parent_source": (d / f"controller_v{parent_version}.py").read_text()
            if parent_version is not None and (d / f"controller_v{parent_version}.py").exists() else None,
            "machine_card": card.read_text() if card.exists() else extra.get("machine_card"),
            "diff_from_parent": diff_path.read_text() if diff_path is not None and diff_path.exists() else None,
        })
    return out


def _strip_traces(obj: dict[str, Any]) -> dict[str, Any]:
    o = dict(obj)
    if isinstance(o.get("episodes"), list):
        o["episodes"] = [{k: v for k, v in ep.items() if k != "trace"} for ep in o["episodes"]]
    if "trace" in o:
        o.pop("trace")
    return o


def evaluations(d: Path, traces: str = "all") -> dict[str, Any]:
    """All trusted evaluation artifacts. ``traces``: all | disturbance | none."""
    def load(pattern: str, kind: str) -> list[dict[str, Any]]:
        items = []
        for p in sorted(d.glob(pattern)):
            m = re.search(r"_v(\d+)\.json$", p.name)
            data = _read_json(p)
            if data is None:
                continue
            keep = traces == "all" or (traces == "disturbance" and kind in {"disturbance"})
            items.append({"file": p.name, "kind": kind, "version": int(m.group(1)) if m else None,
                          "data": data if keep else _strip_traces(data)})
        items.sort(key=lambda x: x["version"] or 0)
        return items

    mon = _read_json(d / "monitoring.json")
    if mon is not None and traces == "none":
        mon = _strip_traces(mon)
    return {
        "heldout": load("evaluation_v*.json", "heldout"),
        "disturbance": load("evaluation_disturbance_v*.json", "disturbance"),
        "adaptation": load("adaptation_v*.json", "adaptation"),
        "monitoring": mon,
        "repair_verdicts": repair_verdicts(d),
        "protocol": protocol(d),
        "twin_fit": _read_json(d / "twin_fit.json"),
    }


RULE_CHANGE_NOTE = ("Recorded verdict under the promotion rule in force at run time: {reason}. "
                    "Under the current rule this candidate meets Gate 3.")


def recorded_outcome(d: Path) -> dict[str, Any]:
    """The run's own recorded verdict (stage + reason). Never rewritten."""
    res = read_result(d)
    events = read_events(d)
    stages = [e for e in events if e.get("kind") == "stage"]
    if res is not None:
        hist = res.get("stage_history") or []
        last = hist[-1] if hist else {}
        return {"stage": res.get("stage"), "reason": last.get("reason"), "source": "result.json",
                "final": res.get("stage") in FINAL_STAGES}
    last = stages[-1] if stages else {}
    return {"stage": last.get("to", "NEW"), "reason": last.get("reason"), "source": "event_log",
            "final": last.get("to") in FINAL_STAGES}


def protocol(d: Path) -> dict[str, Any]:
    res = read_result(d) or {}
    started = next((e for e in read_events(d) if e.get("kind") == "run_started"), {})
    return {"prompt_version": res.get("prompt_version") or started.get("prompt_version"),
            "prompt_hash": res.get("prompt_hash") or started.get("prompt_hash")}


def repair_verdicts(d: Path) -> list[dict[str, Any]]:
    """Per repair candidate: Gate 3 (adaptation comparison, the current promotion rule), nominal
    G2 after repair (reported, not gated), and the run's recorded outcome, side by side."""
    res = read_result(d) or {}
    cand_status = {c.get("version"): c.get("status") for c in res.get("candidates") or []}
    cand_id = {c.get("version"): c.get("candidate_id") for c in res.get("candidates") or []}
    outcome = recorded_outcome(d)
    out = []
    for p in sorted(d.glob("adaptation_v*.json"), key=lambda x: int(re.search(r"_v(\d+)\.json$", x.name).group(1))):
        v = int(re.search(r"_v(\d+)\.json$", p.name).group(1))
        a = _read_json(p) or {}
        cmp = a.get("comparison") or {}
        ev = _read_json(d / f"evaluation_v{v}.json") or {}
        g3 = cmp.get("gate_passed")
        status = cand_status.get(v)
        disagrees = bool(g3) and outcome["final"] and status != "approved"
        out.append({
            "version": v,
            "candidate_id": cand_id.get(v) or f"{d.name}-v{v}",
            "gate3_passed": g3,
            "gate3_reasons": cmp.get("reasons") or [],
            "n_improved": cmp.get("n_improved"),
            "median_reduction": cmp.get("median_reduction"),
            "nominal_after_repair_passed": ev.get("gate_passed", a.get("nominal_gate")),
            "nominal_after_repair_gated": False,
            "diagnosis_category": a.get("diagnosis_category"),
            "diagnosis_correct": a.get("diagnosis_correct"),
            "recorded_candidate_status": status,
            "recorded_outcome": outcome,
            "verdict_disagrees": disagrees,
            "note": RULE_CHANGE_NOTE.format(reason=outcome.get("reason") or outcome.get("stage")) if disagrees else None,
        })
    return out


def experiments(d: Path) -> list[dict[str, Any]]:
    data = _read_json(d / "experiments.json")
    if not isinstance(data, list):
        return []
    out = []
    for e in data:
        out.append({"id": e.get("id"), "phase": e.get("phase", "discovery"), "status": e.get("status"),
                    "t_start": e.get("t_start"), "verdict": e.get("verdict"),
                    "command_u": (e.get("proposal") or {}).get("command_u"),
                    "duration_s": (e.get("proposal") or {}).get("duration_s"),
                    "command_before": e.get("command_before"),
                    "seconds_since_command_last_changed_at_start": e.get("seconds_since_command_last_changed_at_start"),
                    "n_samples": len(e.get("samples") or [])})
    return out


_TANK_DISPLAY = {"name": "tank", "dt": 0.1, "target": 0.6, "band": [0.55, 0.65], "y_unit": "level fraction",
                 "y_scale": 1.0, "y_offset": 0.0, "eval_plant": "simulator", "operator_disturbance": False}


def _trace_profile_name(d: Path) -> str | None:
    mon = _read_json(d / "monitoring.json")
    name = ((mon or {}).get("trace") or {}).get("meta", {}).get("profile") if mon else None
    if name:
        return name
    for p in sorted(d.glob("evaluation_v*.json")):
        ev = _read_json(p) or {}
        for ep in ev.get("episodes") or []:
            name = ((ep.get("trace") or {}).get("meta") or {}).get("profile")
            if name:
                return name
    return None


def display_profile(d: Path) -> dict[str, Any]:
    """How to display this run's y. Order: result.json.profile -> run_started.profile -> profile name in
    stored trace meta resolved against the frozen definitions in backend/profiles.py -> tank (runs that
    predate profiles). Soft/hard limits come from the constraints the agent was actually shown."""
    res = read_result(d) or {}
    started = next((e for e in read_events(d) if e.get("kind") == "run_started"), {})
    prof, source = res.get("profile"), "result.json"
    if not prof:
        prof, source = started.get("profile"), "run_started"
    if not prof:
        name = _trace_profile_name(d)
        if name:
            try:
                from backend.profiles import get_profile
                p = get_profile(name)
                prof = {"name": p.name, "dt": p.dt, "target": p.target, "band": list(p.band), "y_unit": p.y_unit,
                        "y_scale": p.y_scale, "y_offset": p.y_offset, "episode_s": p.episode_s, "settle_s": p.settle_s,
                        "eval_plant": "twin" if (d / "twin_fit.json").exists() else "simulator",
                        "operator_disturbance": None}
                source = "trace_meta+profiles.py"
            except (ImportError, ValueError):
                prof = None
    if not prof:
        prof, source = dict(_TANK_DISPLAY), "default_tank"
    out = dict(prof)
    out["source"] = source
    snaps = sorted((d / "agent_view_snapshots").glob("*.json")) if (d / "agent_view_snapshots").is_dir() else []
    cons = ((_read_json(snaps[0]) or {}).get("constraints") or {}) if snaps else {}
    out["soft_high_limit"] = cons.get("soft_high_limit", 0.85)
    out["hard_cutoff"] = cons.get("hard_cutoff_forces_u_to_zero_at", cons.get("hard_cutoff", 0.90))
    return out


def ledger(d: Path) -> Any:
    data = _read_json(d / "hypothesis_ledger.json")
    if data is not None:
        return data
    # Not yet persisted (written at phase end): reconstruct from ledger events.
    return [{"after_experiment": None, "ts": e["ts"], "hypotheses": e.get("hypotheses", []), "from_event_seq": e["seq"]}
            for e in read_events(d) if e.get("kind") == "ledger"]


def export_zip(d: Path) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for p in sorted(d.rglob("*")):
            if p.is_file():
                z.write(p, arcname=f"{d.name}/{p.relative_to(d)}")
    return buf.getvalue()
