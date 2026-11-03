"""Independent audit of one recorded run bundle. A judge can run this on the bundle alone.

  uv run python scripts/audit_run.py <run_id> [--root artifacts/runs] [--json]

Checks (each prints PASS / FAIL / WARN; exit status is non-zero on any FAIL):
  1. every controller_vN.py sha256 + length matches its meta.json, and result.json lists the same candidates
  2. every agent_view_snapshots/*.json passes backend.agent.view.find_leaks
  3. model_calls.jsonl exists; ok calls use muse-* model ids (MOCK flagged); totals match result.json model_usage
  4. event_log.jsonl seq strictly increasing (contiguous); stage transitions follow the allowed machine
  5. each candidate_registered event's sha256 / byte_length matches the stored file
  6. registered source == source_code in the authoring model call's response_text (byte-identical): authorship
  7. no disturbance family name appears in any model request message
  8. board_verification.json (only when present; otherwise skipped = pass): each trial's controller_sha256
     matches a registered candidate's meta.json hash; 0 <= u_applied <= 1 on every step; no interlock trip;
     a non-empty post-change window; no step with t < 0
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.agent.view import find_leaks
from backend.evaluation.config import DISTURBANCE_FAMILIES

MOCK_MODEL_PREFIX = "MOCK"
SOURCE_STAGES = ("authoring", "revising", "fixing", "adapting")
_SOURCE_RE = re.compile(r"^controller_v(?P<ver>[1-9][0-9]*)\.py$")

# Stage machine. Core edges as specified for the protocol (plan 6.1):
CORE_TRANSITIONS: set[tuple[str, str]] = {
    ("NEW", "EXPLORING"), ("EXPLORING", "GENERATING"), ("GENERATING", "STATIC_CHECK"),
    ("STATIC_CHECK", "SANDBOX_CHECK"), ("SANDBOX_CHECK", "EVALUATING"),
    ("EVALUATING", "REVISING"), ("EVALUATING", "DEPLOYABLE"), ("EVALUATING", "FAILED"),
    ("DEPLOYABLE", "MONITORING"), ("MONITORING", "ADAPTING"), ("MONITORING", "COMPLETE"),
    ("ADAPTING", "STATIC_CHECK"), ("REVISING", "STATIC_CHECK"),
    ("EVALUATING", "ADAPTING"), ("EVALUATING", "COMPLETE"),
}
# Edges the orchestrator (backend/agent/orchestrator.py) also produces; listed explicitly, not wildcarded:
ORCHESTRATOR_TRANSITIONS: dict[tuple[str, str], str] = {
    ("STATIC_CHECK", "STATIC_CHECK"): "contract-fix loop / rejected candidate re-registered (_validate_contract)",
    ("SANDBOX_CHECK", "STATIC_CHECK"): "sandbox interface failure -> fix -> re-check (_validate_contract)",
    ("STATIC_CHECK", "ADAPTING"): "rejected repair candidate -> next adaptation attempt (_adapt)",
    ("ADAPTING", "ADAPTING"): "protocol v1.1: re-identification experiments done -> first revision attempt (_adapt)",
    ("SANDBOX_CHECK", "ADAPTING"): "rejected repair candidate -> next adaptation attempt (_adapt)",
    ("STATIC_CHECK", "FAILED"): "candidate budget exhausted after a rejected candidate",
    ("SANDBOX_CHECK", "FAILED"): "candidate budget exhausted after a rejected candidate",
    ("REVISING", "FAILED"): "candidate budget exhausted after a failed gate",
    ("EXPLORING", "FAILED"): "model error (MuseError)",
    ("GENERATING", "FAILED"): "model error (MuseError) or zero candidate budget",
    ("MONITORING", "FAILED"): "model error / candidate budget exhausted during adaptation",
    ("ADAPTING", "FAILED"): "model error (MuseError) during adaptation",
}
TERMINAL = {"COMPLETE", "FAILED", "STOPPED"}


def allowed(frm: str, to: str) -> bool:
    if to == "STOPPED":
        return frm not in TERMINAL  # any (non-terminal) -> STOPPED
    return (frm, to) in CORE_TRANSITIONS or (frm, to) in ORCHESTRATOR_TRANSITIONS


@dataclass
class Check:
    number: int
    name: str
    status: str = "PASS"  # PASS | FAIL | WARN
    details: list[str] = field(default_factory=list)

    def fail(self, msg: str) -> None:
        self.status = "FAIL"
        self.details.append(msg)

    def warn(self, msg: str) -> None:
        if self.status != "FAIL":
            self.status = "WARN"
        self.details.append(msg)

    def note(self, msg: str) -> None:
        self.details.append(msg)


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def _versions(run_dir: Path) -> list[int]:
    return sorted(int(m.group("ver")) for p in run_dir.iterdir() if (m := _SOURCE_RE.match(p.name)))


# ------------------------------------------------------------------------------------------------ checks
def check_hashes(run_dir: Path, result: dict[str, Any]) -> Check:
    c = Check(1, "controller hashes match meta.json and result.json")
    vers = _versions(run_dir)
    if not vers:
        c.warn("no controller_vN.py in bundle")
    rc = {x["candidate_id"]: x for x in result.get("candidates") or []}
    seen = set()
    for v in vers:
        src = run_dir / f"controller_v{v}.py"
        meta_p = run_dir / f"controller_v{v}.meta.json"
        data = src.read_bytes()
        if not meta_p.exists():
            c.fail(f"v{v}: missing {meta_p.name}")
            continue
        meta = json.loads(meta_p.read_text())
        cid = f"{run_dir.name}-v{v}"
        seen.add(cid)
        if meta.get("id") != cid:
            c.fail(f"v{v}: meta id {meta.get('id')!r} != {cid!r}")
        if _sha(data) != meta.get("sha256") or len(data) != meta.get("byte_length"):
            c.fail(f"v{v}: sha256 {_sha(data)[:16]}… len {len(data)} != meta {str(meta.get('sha256'))[:16]}… "
                   f"len {meta.get('byte_length')}")
        else:
            c.note(f"v{v}: sha256 {_sha(data)[:16]}… ({len(data)} B) ok")
        r = rc.get(cid)
        if r is None:
            c.fail(f"v{v}: not listed in result.json candidates")
        else:
            for k_meta, k_res in (("model_id", "model_id"), ("prompt_hash", "prompt_hash"), ("parent_id", "parent_id")):
                if meta.get(k_meta) != r.get(k_res):
                    c.fail(f"v{v}: {k_meta} meta={meta.get(k_meta)!r} result={r.get(k_res)!r}")
            sub_src = (r.get("submission") or {}).get("source_code")
            if sub_src is not None and sub_src.encode("utf-8") != data:
                c.fail(f"v{v}: result.json submission.source_code differs from controller_v{v}.py")
    for cid in set(rc) - seen:
        c.fail(f"result.json lists {cid} but no controller file exists")
    return c


def check_snapshots(run_dir: Path) -> Check:
    c = Check(2, "agent view snapshots pass find_leaks")
    snaps = sorted((run_dir / "agent_view_snapshots").glob("*.json"))
    if not snaps:
        c.fail("no agent_view_snapshots/*.json")
    for p in snaps:
        try:
            view = json.loads(p.read_text())
        except json.JSONDecodeError as e:
            c.fail(f"{p.name}: unreadable ({e})")
            continue
        leaks = find_leaks(view)
        if leaks:
            c.fail(f"{p.name}: {'; '.join(leaks[:5])}")
    if snaps and c.status == "PASS":
        c.note(f"{len(snaps)} snapshot(s) clean")
    return c


def check_model_calls(run_dir: Path, result: dict[str, Any], events: list[dict[str, Any]]) -> tuple[Check, list]:
    c = Check(3, "model_calls.jsonl: muse-* models, totals match result.json")
    path = run_dir / "model_calls.jsonl"
    is_mock = result.get("agent_mode") == "mock"
    if not path.exists():
        (c.warn if is_mock else c.fail)("model_calls.jsonl missing" + (" (MOCK run: mock agent writes none)"
                                                                       if is_mock else ""))
        return c, []
    calls = _jsonl(path)
    ok = [x for x in calls if x.get("ok")]
    if not ok:
        c.fail("no ok calls")
    models = sorted({str(x.get("model")) for x in calls})
    for m in models:
        if m.startswith(MOCK_MODEL_PREFIX):
            c.warn(f"model id {m!r}: MOCK, not Muse output")
        elif not m.startswith("muse-") or "contributor" in m:
            c.fail(f"model id {m!r} is not a muse-* model")
    usage = result.get("model_usage") or {}
    sums = {
        "calls": len(calls), "failed_calls": sum(1 for x in calls if not x.get("ok")),
        "prompt_tokens": sum(int(x.get("prompt_tokens") or 0) for x in calls),
        "completion_tokens": sum(int(x.get("completion_tokens") or 0) for x in calls),
        "reasoning_tokens": sum(int(x.get("reasoning_tokens") or 0) for x in calls),
        "cost_usd": sum(float(x.get("cost_usd") or 0.0) for x in calls),
    }
    for k, v in sums.items():
        rv = usage.get(k)
        same = (rv is not None and math.isclose(float(rv), float(v), rel_tol=1e-9, abs_tol=1e-9))
        if not same:
            c.fail(f"{k}: model_calls.jsonl sum {v} != result.json model_usage {rv}")
    ev_calls = [e for e in events if e.get("kind") == "model_call"]
    if len(ev_calls) != len(ok):
        c.fail(f"event_log has {len(ev_calls)} model_call events but model_calls.jsonl has {len(ok)} ok calls")
    if c.status != "FAIL":
        c.note(f"{len(calls)} calls ({sums['failed_calls']} failed, retried), models {models}, "
               f"tokens in/out {sums['prompt_tokens']}/{sums['completion_tokens']}, est. ${sums['cost_usd']:.4f}")
    return c, calls


def check_events(run_dir: Path, result: dict[str, Any], events: list[dict[str, Any]]) -> Check:
    c = Check(4, "event log ordered; stage transitions follow the machine")
    if not events:
        c.fail("event_log.jsonl missing or empty")
        return c
    prev_seq, prev_ts = 0, -math.inf
    for e in events:
        s = e.get("seq")
        if not isinstance(s, int) or s <= prev_seq:
            c.fail(f"seq not strictly increasing at seq={s} (previous {prev_seq})")
        elif s != prev_seq + 1:
            c.fail(f"seq gap: {prev_seq} -> {s} (event deleted?)")
        if float(e.get("ts", 0)) < prev_ts:
            c.fail(f"ts goes backwards at seq={s}")
        if e.get("run_id") not in (None, run_dir.name):
            c.fail(f"seq={s}: run_id {e.get('run_id')!r} != {run_dir.name!r}")
        prev_seq, prev_ts = s if isinstance(s, int) else prev_seq, float(e.get("ts", prev_ts))
    stages = [e for e in events if e.get("kind") == "stage"]
    cur = "NEW"
    used_extra: set[str] = set()
    for e in stages:
        frm, to = e.get("from"), e.get("to")
        if frm != cur:
            c.fail(f"seq={e['seq']}: transition from {frm} but machine is in {cur}")
        if cur in TERMINAL:
            c.fail(f"seq={e['seq']}: transition out of terminal stage {cur}")
        if not allowed(str(frm), str(to)):
            c.fail(f"seq={e['seq']}: {frm} -> {to} is not an allowed transition")
        elif (frm, to) in ORCHESTRATOR_TRANSITIONS:
            used_extra.add(f"{frm}->{to} ({ORCHESTRATOR_TRANSITIONS[(frm, to)]})")
        cur = str(to)
    hist = [(h.get("from"), h.get("to")) for h in result.get("stage_history") or []]
    logged = [(e.get("from"), e.get("to")) for e in stages]
    if hist != logged:
        c.fail(f"result.json stage_history ({len(hist)}) differs from event_log stage events ({len(logged)})")
    if result.get("stage") != cur:
        c.fail(f"result.json stage {result.get('stage')!r} != final logged stage {cur!r}")
    if c.status == "PASS":
        c.note(f"{len(events)} events, {len(stages)} transitions: " + " → ".join(["NEW"] + [t for _, t in logged]))
    for u in sorted(used_extra):
        c.note(f"orchestrator edge used: {u}")
    return c


def check_registered_events(run_dir: Path, events: list[dict[str, Any]]) -> Check:
    c = Check(5, "candidate_registered events match stored files")
    reg = [e for e in events if e.get("kind") == "candidate_registered"]
    vers = _versions(run_dir)
    by_ver = {}
    for e in reg:
        v = int(e.get("version"))
        if v in by_ver:
            c.fail(f"v{v} registered twice (seq {by_ver[v]['seq']} and {e['seq']})")
        by_ver[v] = e
        p = run_dir / f"controller_v{v}.py"
        if not p.exists():
            c.fail(f"seq={e['seq']}: {p.name} missing")
            continue
        data = p.read_bytes()
        if e.get("sha256") != _sha(data) or int(e.get("byte_length", -1)) != len(data):
            c.fail(f"v{v}: event sha256 {str(e.get('sha256'))[:16]}… != file {_sha(data)[:16]}…")
        if e.get("candidate_id") != f"{run_dir.name}-v{v}":
            c.fail(f"v{v}: event candidate_id {e.get('candidate_id')!r}")
    for v in set(vers) - set(by_ver):
        c.fail(f"controller_v{v}.py has no candidate_registered event")
    if c.status == "PASS":
        c.note(f"{len(reg)} registration event(s) match")
    return c


def check_authorship(run_dir: Path, calls: list[dict[str, Any]], is_mock: bool) -> Check:
    c = Check(6, "registered source == model response source_code (byte-identical)")
    vers = _versions(run_dir)
    if not calls:
        (c.warn if is_mock else c.fail)("no model calls to compare against" + (" (MOCK run)" if is_mock else ""))
        return c
    sourced = []
    for i, x in enumerate(calls):
        if not x.get("ok") or x.get("stage") not in SOURCE_STAGES:
            continue
        try:
            body = json.loads(x.get("response_text") or "")
        except json.JSONDecodeError:
            c.fail(f"call #{i} ({x.get('stage')}) ok but response_text is not JSON")
            continue
        if not isinstance(body, dict) or "source_code" not in body:
            c.fail(f"call #{i} ({x.get('stage')}) has no source_code")
            continue
        sourced.append((i, x, body["source_code"]))
    if len(sourced) != len(vers):
        c.fail(f"{len(sourced)} source-bearing ok model calls vs {len(vers)} registered controllers")
    for (i, x, src), v in zip(sourced, vers):
        data = (run_dir / f"controller_v{v}.py").read_bytes()
        if src.encode("utf-8") == data:
            c.note(f"v{v} == call #{i} [{x.get('stage')}, {x.get('model')}] response source_code "
                   f"({len(data)} B, sha256 {_sha(data)[:16]}…)")
        else:
            c.fail(f"v{v} differs from call #{i} [{x.get('stage')}] response source_code")
    return c


def check_family_names(calls: list[dict[str, Any]], is_mock: bool, family_used: str | None) -> Check:
    c = Check(7, "no disturbance family name in any model request")
    if not calls:
        (c.warn if is_mock else c.fail)("no model_calls.jsonl to scan" + (" (MOCK run)" if is_mock else ""))
        return c
    names = sorted(DISTURBANCE_FAMILIES)
    n_msgs = 0
    for i, x in enumerate(calls):
        for j, m in enumerate(x.get("request_messages") or []):
            n_msgs += 1
            text = json.dumps(m) if not isinstance(m, dict) else str(m.get("content", ""))
            low = text.lower()
            for f in names:
                if f in low or f.replace("_", " ") in low:
                    c.fail(f"call #{i} message {j} ({m.get('role') if isinstance(m, dict) else '?'}) contains {f!r}")
    if c.status == "PASS":
        c.note(f"{n_msgs} request messages scanned for {names}; family used in run: {family_used!r}")
    return c


def check_board_verification(run_dir: Path) -> Check:
    c = Check(8, "board_verification.json: registered hashes, actuator in [0,1], no interlock, post window")
    p = run_dir / "board_verification.json"
    if not p.exists():
        c.note("skipped: no board_verification.json in bundle")
        return c
    try:
        bv = json.loads(p.read_text())
    except json.JSONDecodeError as e:
        c.fail(f"unreadable ({e})")
        return c
    registered: dict[str, str] = {}
    for v in _versions(run_dir):
        mp = run_dir / f"controller_v{v}.meta.json"
        if mp.exists():
            registered[str(json.loads(mp.read_text()).get("sha256"))] = f"v{v}"
    trials = bv.get("trials") or []
    if not trials:
        c.fail("no trials")
    if bv.get("fake_board"):
        c.warn("fake_board=true: test-only run on an in-process fake board, not hardware evidence")
    pre_s = bv.get("pre_s")
    for t in trials:
        label = t.get("label")
        sha = str(t.get("controller_sha256"))
        if sha not in registered:
            c.fail(f"{label}: controller_sha256 {sha[:16]}… matches no registered candidate")
        steps = (t.get("trace") or {}).get("steps") or []
        bad_u = [s.get("t") for s in steps if not (isinstance(s.get("u_applied"), (int, float))
                                                    and 0.0 <= float(s["u_applied"]) <= 1.0)]
        if bad_u:
            c.fail(f"{label}: {len(bad_u)} step(s) with u_applied outside [0, 1] (first t={bad_u[0]})")
        neg = [s.get("t") for s in steps if float(s.get("t", 0.0)) < 0.0]
        if neg:
            c.fail(f"{label}: {len(neg)} step(s) with t < 0")
        if t.get("interlock_hit") is not False:
            c.fail(f"{label}: interlock_hit={t.get('interlock_hit')!r}")
        d_at = (t.get("trace") or {}).get("disturbance_at", pre_s)
        n_post = sum(1 for s in steps if d_at is not None and float(s.get("t", -1.0)) >= float(d_at) - 1e-9)
        if n_post == 0:
            c.fail(f"{label}: empty post-change window (disturbance_at={d_at})")
        if c.status != "FAIL":
            c.note(f"{label} = {registered.get(sha, '?')} sha256 {sha[:16]}…, {len(steps)} steps, {n_post} post-change, "
                   f"post_mae={t.get('post_mae')}")
    if bv.get("comparison"):
        c.note(f"comparison: {bv['comparison']}")
    return c


# ------------------------------------------------------------------------------------------------ driver
def audit(run_dir: Path) -> list[Check]:
    run_dir = Path(run_dir)
    rp = run_dir / "result.json"
    if not rp.exists():
        c = Check(0, "result.json present")
        c.fail(f"{rp} missing (run in progress or crashed)")
        return [c]
    result = json.loads(rp.read_text())
    ev_path = run_dir / "event_log.jsonl"
    events = _jsonl(ev_path) if ev_path.exists() else []
    is_mock = result.get("agent_mode") == "mock"
    family = (result.get("monitoring") or {}).get("disturbance_family")
    c3, calls = check_model_calls(run_dir, result, events)
    return [
        check_hashes(run_dir, result),
        check_snapshots(run_dir),
        c3,
        check_events(run_dir, result, events),
        check_registered_events(run_dir, events),
        check_authorship(run_dir, calls, is_mock),
        check_family_names(calls, is_mock, family),
        check_board_verification(run_dir),
    ]


def format_checks(run_id: str, checks: list[Check], result: dict[str, Any] | None = None) -> str:
    lines = [f"Praxion run audit: {run_id}"]
    if result:
        lines.append(f"agent_mode={result.get('agent_mode')} model={result.get('model_id')} "
                     f"prompt={result.get('prompt_version')} final_stage={result.get('stage')}")
        if result.get("agent_mode") == "mock":
            lines.append("*** MOCK RUN: plumbing only; nothing here is Muse output ***")
    for c in checks:
        lines.append(f"[{c.status}] {c.number}. {c.name}")
        for d in c.details:
            lines.append(f"       - {d}")
    n_fail = sum(1 for c in checks if c.status == "FAIL")
    n_warn = sum(1 for c in checks if c.status == "WARN")
    lines.append(f"RESULT: {'FAIL' if n_fail else 'PASS'} ({len(checks) - n_fail - n_warn} pass, "
                 f"{n_warn} warn, {n_fail} fail)")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Independent audit of a recorded Praxion run bundle.")
    ap.add_argument("run_id")
    ap.add_argument("--root", default="artifacts/runs")
    ap.add_argument("--json", action="store_true", help="machine-readable output")
    args = ap.parse_args(argv)
    run_dir = Path(args.root) / args.run_id
    if not run_dir.is_dir():
        print(f"error: {run_dir} not found", file=sys.stderr)
        return 2
    checks = audit(run_dir)
    rp = run_dir / "result.json"
    result = json.loads(rp.read_text()) if rp.exists() else None
    if args.json:
        print(json.dumps({"run_id": args.run_id, "checks": [asdict(c) for c in checks],
                          "passed": all(c.status != "FAIL" for c in checks)}, indent=1))
    else:
        print(format_checks(args.run_id, checks, result))
    return 1 if any(c.status == "FAIL" for c in checks) else 0


if __name__ == "__main__":
    raise SystemExit(main())
