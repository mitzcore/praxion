"""Benchmark, ablation and gate tables regenerated from stored runs (plan sections 3, 6.9, 10). TRUSTED.

One call reproduces every number in ``docs/BENCHMARKS.md``:

* discover recorded runs under ``<artifact_root>/runs/*/result.json`` (mock runs skipped unless asked),
* verify every registered candidate's hash through the Registry (a failing hash aborts that run's rows),
* score EVERY candidate fresh on the frozen held-out scenarios and on every disturbance family in
  ``DISTURBANCE_FAMILIES`` (sandboxed: docker, or subprocess_dev_only for development),
* score the transparent baselines on the same machine (plant seed) and the same scenarios,
* derive the ablation rows, the gate table and the cross-run summary.

Nothing here is shown to the model. Fresh reports are cached under ``<cache_dir>`` keyed by the candidate's
source sha256, the suite and the plant seed; a cache entry is only reused when the evaluator fingerprint
(hash of the frozen config and the scoring code) and the sandbox mode match.
"""
from __future__ import annotations

import hashlib
import json
import math
import statistics
import time
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from backend.controller.registry import Candidate, Registry
from backend.evaluation import config as cfg
from backend.evaluation.baselines import SLOW_PID_TUNING, OnOffController, PIDController
from backend.evaluation.report import EpisodeResult, EvaluationReport
from backend.evaluation.suite import compare_adaptation, evaluate_disturbance, evaluate_heldout
from backend.schemas import Metrics, Trace

REPO_ROOT = Path(__file__).resolve().parents[2]

# Files whose content determines every score. A change to any of them invalidates the cache.
_FINGERPRINT_FILES = (
    "backend/evaluation/config.py",
    "backend/evaluation/suite.py",
    "backend/evaluation/metrics.py",
    "backend/evaluation/baselines.py",
    "backend/plant/tank_sim.py",
    "backend/plant/base.py",
    "backend/safety/supervisor.py",
    "backend/safety/envelope.py",
    "backend/controller/runtime.py",
    "backend/controller/sandbox_runner.py",
)

FROZEN_KEYS = (
    "TARGET", "BAND", "EPISODE_S", "SETTLE_S", "HELDOUT_SEEDS", "DISTURBANCE_SEEDS", "DISTURBANCE_AT_S",
    "DISTURBANCE_EPISODE_S", "GATE2_MIN_PASS", "GATE2_MIN_INBAND", "GATE3_MIN_PASS", "GATE3_MIN_MAE_REDUCTION",
    "IN_BAND_SUSTAIN_S", "DISTURBANCE_FAMILIES",
)

BASELINE_LABELS = {
    "fixed_pid": "fixed PID",
    "fixed_onoff": "fixed on/off",
    "slow_pid": "slow PID",
}
BASELINE_SPECS: dict[str, tuple[Callable[[], Any], dict[str, Any]]] = {
    "fixed_pid": (lambda: PIDController(), {"class": "PIDController", "kp": 3.0, "ki": 0.15, "kd": 0.0}),
    "fixed_onoff": (lambda: OnOffController(), {"class": "OnOffController", "hysteresis": 0.02}),
    "slow_pid": (lambda: PIDController(**SLOW_PID_TUNING, name="baseline_slow_pid"),
                 {"class": "PIDController", **SLOW_PID_TUNING}),
}
SOURCE_STAGES = ("authoring", "revising", "fixing", "adapting")


class BenchmarkError(RuntimeError):
    pass


# =========================================================================== small helpers
def frozen_config() -> dict[str, Any]:
    return {k: getattr(cfg, k) for k in FROZEN_KEYS}


def evaluator_fingerprint() -> str:
    h = hashlib.sha256()
    h.update(json.dumps(frozen_config(), sort_keys=True, default=str).encode())
    for rel in _FINGERPRINT_FILES:
        p = REPO_ROOT / rel
        h.update(rel.encode())
        h.update(p.read_bytes() if p.exists() else b"<missing>")
    return h.hexdigest()[:16]


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _finite(x: Any) -> bool:
    try:
        return x is not None and math.isfinite(float(x))
    except (TypeError, ValueError):
        return False


def _median(xs: Iterable[Any]) -> float | None:
    vals = [float(x) for x in xs if _finite(x)]
    return float(statistics.median(vals)) if vals else None


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    out = []
    for line in path.read_text().splitlines():
        if line.strip():
            out.append(json.loads(line))
    return out


def _suite_key(suite: str) -> str:
    return suite.replace(":", "_")


# =========================================================================== report cache
@dataclass
class ReportCache:
    """On-disk cache of slim fresh reports: ``<dir>/<sha256>-<suite>-<plant_seed>.json``."""

    directory: Path
    fingerprint: str = field(default_factory=evaluator_fingerprint)
    hits: int = 0
    misses: int = 0

    def path(self, sha: str, suite: str, plant_seed: int) -> Path:
        return self.directory / f"{sha}-{_suite_key(suite)}-{plant_seed}.json"

    def get(self, sha: str, suite: str, plant_seed: int, isolation: str) -> dict[str, Any] | None:
        p = self.path(sha, suite, plant_seed)
        if p.exists():
            try:
                entry = json.loads(p.read_text())
            except json.JSONDecodeError:
                entry = None
            if (entry and entry.get("fingerprint") == self.fingerprint and entry.get("isolation") == isolation
                    and entry.get("source_sha256") == sha):
                self.hits += 1
                return entry["report"]
        self.misses += 1
        return None

    def put(self, sha: str, suite: str, plant_seed: int, isolation: str, report: dict[str, Any]) -> None:
        self.directory.mkdir(parents=True, exist_ok=True)
        entry = {"fingerprint": self.fingerprint, "isolation": isolation, "source_sha256": sha, "suite": suite,
                 "plant_seed": plant_seed, "scored_at": time.time(), "report": report}
        tmp = self.path(sha, suite, plant_seed).with_suffix(".tmp")
        tmp.write_text(json.dumps(entry, default=str))
        tmp.replace(self.path(sha, suite, plant_seed))


def slim_report(report: EvaluationReport) -> dict[str, Any]:
    """Everything the tables need, without traces (a full report is megabytes)."""
    pdm = report.comparison.get("post_disturbance_mae") or {}
    return {
        "candidate_id": report.candidate_id,
        "suite": report.suite,
        "gate_name": report.gate_name,
        "gate_passed": report.gate_passed,
        "gate_reasons": list(report.gate_reasons),
        "aggregate": dict(report.aggregate),
        "post_disturbance_mae": {str(k): v for k, v in pdm.items()},
        "episodes": [
            {"index": e.index, "scenario": e.seed, "passed": e.passed, "fail_reasons": list(e.fail_reasons),
             "metrics": e.metrics.model_dump(), "post_disturbance_mae": pdm.get(str(e.index))}
            for e in report.episodes
        ],
    }


def report_from_slim(s: dict[str, Any]) -> EvaluationReport:
    """Rebuild an EvaluationReport good enough for ``compare_adaptation`` (post-MAE is stored per index)."""
    family = s["suite"].split(":", 1)[1] if s["suite"].startswith("disturbance:") else None
    eps = [
        EpisodeResult(index=e["index"], seed=e["scenario"], disturbance_family=family,
                      metrics=Metrics(**e["metrics"]), trace=Trace(dt=0.1, target=cfg.TARGET),
                      passed=e["passed"], fail_reasons=e["fail_reasons"])
        for e in s["episodes"]
    ]
    return EvaluationReport(candidate_id=s["candidate_id"], suite=s["suite"], episodes=eps, aggregate=s["aggregate"],
                            gate_name=s["gate_name"], gate_passed=s["gate_passed"], gate_reasons=s["gate_reasons"],
                            comparison={"post_disturbance_mae": s.get("post_disturbance_mae") or {}})


# =========================================================================== scoring
def _score_suites(
    factory: Callable[[], Any], *, ident: str, key_sha: str, plant_seed: int, isolation: str,
    families: Iterable[str], cache: ReportCache,
) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    suites = ["heldout"] + [f"disturbance:{f}" for f in families]
    for suite in suites:
        hit = cache.get(key_sha, suite, plant_seed, isolation)
        if hit is not None:
            out[suite] = hit
            continue
        if suite == "heldout":
            rep = evaluate_heldout(factory, candidate_id=ident, plant_seed=plant_seed)
        else:
            rep = evaluate_disturbance(factory, suite.split(":", 1)[1], candidate_id=ident, plant_seed=plant_seed)
        slim = slim_report(rep)
        cache.put(key_sha, suite, plant_seed, isolation, slim)
        out[suite] = slim
    return out


def score_candidate(source: str, candidate_id: str, *, plant_seed: int, sandbox_mode: str, cache: ReportCache,
                    families: Iterable[str] | None = None) -> dict[str, dict[str, Any]]:
    from backend.controller.sandbox import make_sandbox

    sha = _sha256(source.encode("utf-8"))
    return _score_suites(lambda: make_sandbox(source, name=candidate_id, mode=sandbox_mode), ident=candidate_id,
                         key_sha=sha, plant_seed=plant_seed, isolation=sandbox_mode,
                         families=list(families or cfg.DISTURBANCE_FAMILIES), cache=cache)


def baseline_key(name: str) -> str:
    _, params = BASELINE_SPECS[name]
    bsrc = (REPO_ROOT / "backend/evaluation/baselines.py").read_bytes()
    return _sha256(json.dumps({"baseline": name, "params": params}, sort_keys=True).encode() + bsrc)


def score_baseline(name: str, *, plant_seed: int, cache: ReportCache,
                   families: Iterable[str] | None = None) -> dict[str, dict[str, Any]]:
    factory, _ = BASELINE_SPECS[name]
    return _score_suites(factory, ident=f"baseline:{name}", key_sha=baseline_key(name), plant_seed=plant_seed,
                         isolation="trusted", families=list(families or cfg.DISTURBANCE_FAMILIES), cache=cache)


# =========================================================================== run discovery
@dataclass
class RunInfo:
    run_id: str
    dir: Path
    result: dict[str, Any]
    is_mock: bool
    plant_seed: int | None
    plant_seed_source: str


def plant_seed_from_run(run_dir: Path) -> int | None:
    """Plant seed from the trusted evaluator audit entries of the first stored evaluation report."""
    for name in sorted(run_dir.glob("evaluation_v*.json"), key=lambda p: p.name):
        try:
            audit = json.loads(name.read_text()).get("comparison", {}).get("audit") or []
        except (OSError, json.JSONDecodeError):
            continue
        seeds = {a.get("plant_seed") for a in audit if isinstance(a, dict)}
        seeds.discard(None)
        if len(seeds) == 1:
            return int(seeds.pop())
        if len(seeds) > 1:
            raise BenchmarkError(f"{run_dir.name}: inconsistent plant seeds in {name.name}: {sorted(seeds)}")
    return None


def discover_runs(runs_root: Path, *, include_mock: bool, plant_seed_override: int | None = None,
                  run_ids: Iterable[str] | None = None) -> tuple[list[RunInfo], list[dict[str, str]]]:
    """Runs with a result.json. Returns (runs, skipped[{run_id, reason}])."""
    wanted = set(run_ids or [])
    runs: list[RunInfo] = []
    skipped: list[dict[str, str]] = []
    if not runs_root.is_dir():
        return runs, skipped
    for d in sorted(p for p in runs_root.iterdir() if p.is_dir()):
        if wanted and d.name not in wanted:
            continue
        rp = d / "result.json"
        if not rp.exists():
            skipped.append({"run_id": d.name, "reason": "no result.json (in progress or crashed)"})
            continue
        result = json.loads(rp.read_text())
        is_mock = result.get("agent_mode") == "mock"
        if is_mock and not include_mock:
            skipped.append({"run_id": d.name, "reason": "mock run (excluded; use --include-mock)"})
            continue
        seed = plant_seed_from_run(d)
        src = "evaluation_v*.json comparison.audit"
        if seed is None:
            seed, src = plant_seed_override, "--plant-seed override"
        if seed is None:
            skipped.append({"run_id": d.name, "reason": "plant seed unknown (no evaluation report); pass --plant-seed"})
            continue
        runs.append(RunInfo(d.name, d, result, is_mock, seed, src))
    return runs, skipped


# =========================================================================== per-run facts
def _model_call_stats(run: RunInfo, upto_ts: float | None = None) -> dict[str, Any]:
    calls = _read_jsonl(run.dir / "model_calls.jsonl")
    if upto_ts is not None:
        calls = [c for c in calls if float(c.get("ts", 0)) <= upto_ts + 1e-6]
    if not calls and run.is_mock:
        usage = run.result.get("model_usage") or {}
        return {"calls": int(usage.get("calls", 0)) if upto_ts is None else None, "ok_calls": None,
                "cost_usd": 0.0, "source": "result.json model_usage (MOCK, no model_calls.jsonl)"}
    return {"calls": len(calls), "ok_calls": sum(1 for c in calls if c.get("ok")),
            "cost_usd": float(sum(float(c.get("cost_usd") or 0.0) for c in calls)), "source": "model_calls.jsonl"}


def _experiment_stats(result: dict[str, Any]) -> dict[str, Any]:
    exps = result.get("experiments") or []
    completed = [e for e in exps if e.get("status") == "completed"]
    distinct = {(round(float(e["proposal"].get("command_u", math.nan)), 4),
                 round(float(e["proposal"].get("duration_s", math.nan)), 3)) for e in completed}
    tied = [e for e in completed if str(e["proposal"].get("uncertainty_targeted") or "").strip()]
    return {"total": len(exps), "completed": len(completed), "distinct_completed": len(distinct),
            "tied_to_uncertainty": len(tied)}


def _candidate_status(result: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {c["candidate_id"]: c for c in result.get("candidates") or []}


def verify_candidates(registry: Registry, run_id: str, run_dir: Path) -> tuple[list[Candidate], list[str]]:
    """Registry-listed candidates with their path pinned to this run dir; returns (candidates, failures)."""
    cands, failures = [], []
    for c in registry.list(run_id):
        pinned = c.model_copy(update={"path": run_dir / f"controller_v{c.version}.py"})
        if not registry.verify(pinned):
            failures.append(f"{c.id}: sha256/length mismatch against controller_v{c.version}.meta.json")
        cands.append(pinned)
    return cands, failures


def _variant_metrics(scores: dict[str, dict[str, Any]], family: str) -> dict[str, Any]:
    nom = scores["heldout"]["aggregate"]
    dist = scores[f"disturbance:{family}"]
    dagg = dist["aggregate"]
    lats = [e["metrics"].get("adaptation_latency_s") for e in dist["episodes"]]
    recovered = [x for x in lats if _finite(x)]
    return {
        "nominal_median_mae": nom.get("median_mae"),
        "nominal_in_band": nom.get("mean_in_band_fraction"),
        "nominal_energy": nom.get("median_actuation_energy"),
        "nominal_passed": f"{int(nom.get('n_passed', 0))}/{int(nom.get('n_episodes', 0))}",
        "post_median_mae": dagg.get("median_post_disturbance_mae"),
        "post_in_band": dagg.get("mean_in_band_fraction"),
        "adaptation_latency_s": _median(recovered),
        "recovered": f"{len(recovered)}/{len(lats)}",
        "overrides_nominal": int(nom.get("total_overrides", 0)),
        "overrides_post": int(dagg.get("total_overrides", 0)),
        "hard_violations_nominal": int(nom.get("total_hard_violations", 0)),
        "hard_violations_post": int(dagg.get("total_hard_violations", 0)),
    }


def benchmark_run(run: RunInfo, *, registry: Registry, sandbox_mode: str, cache: ReportCache,
                  baselines: Iterable[str] = tuple(BASELINE_SPECS), families: Iterable[str] | None = None,
                  progress: Callable[[str], None] | None = None) -> dict[str, Any]:
    say = progress or (lambda _m: None)
    fams = list(families or cfg.DISTURBANCE_FAMILIES)
    result = run.result
    events = _read_jsonl(run.dir / "event_log.jsonl")
    started_ts = next((e["ts"] for e in events if e.get("kind") == "run_started"), None)
    out: dict[str, Any] = {
        "run_id": run.run_id, "mock": run.is_mock, "agent_mode": result.get("agent_mode"),
        "model_id": result.get("model_id"), "prompt_version": result.get("prompt_version"),
        "prompt_hash": result.get("prompt_hash"), "recorded_sandbox_mode": result.get("sandbox_mode"),
        "plant_seed": run.plant_seed, "plant_seed_source": run.plant_seed_source,
        "final_stage": result.get("stage"),
        "final_stage_reason": (result.get("stage_history") or [{}])[-1].get("reason"),
        "elapsed_s": result.get("elapsed_s"),
        "disturbance_family": (result.get("monitoring") or {}).get("disturbance_family"),
        "experiments": _experiment_stats(result),
        "aborted": None,
    }
    cands, failures = verify_candidates(registry, run.run_id, run.dir)
    out["hash_failures"] = failures
    if failures:
        out["aborted"] = "candidate hash verification failed: " + "; ".join(failures)
        return out

    status = _candidate_status(result)
    approved = [c for c in cands if status.get(c.id, {}).get("status") == "approved"]
    v1 = approved[0] if approved else None
    final = approved[-1] if approved else None
    reg_events = {e["candidate_id"]: e for e in events if e.get("kind") == "candidate_registered"}
    approve_events = {e["candidate_id"]: e for e in events if e.get("kind") == "candidate_approved"}

    # ---- fresh scores
    cand_scores: dict[str, dict[str, Any]] = {}
    for c in cands:
        say(f"  scoring {c.id} ({sandbox_mode})")
        src = registry.load_source(c.id)
        cand_scores[c.id] = score_candidate(src, c.id, plant_seed=run.plant_seed, sandbox_mode=sandbox_mode,
                                            cache=cache, families=fams)
    base_scores: dict[str, dict[str, Any]] = {}
    for b in baselines:
        say(f"  scoring baseline {b}")
        base_scores[b] = score_baseline(b, plant_seed=run.plant_seed, cache=cache, families=fams)

    out["candidates"] = []
    for c in cands:
        h = cand_scores[c.id]["heldout"]
        rec_path = run.dir / f"evaluation_v{c.version}.json"
        recorded = None
        if rec_path.exists():
            ragg = json.loads(rec_path.read_text()).get("aggregate", {})
            recorded = {"median_mae": ragg.get("median_mae"), "n_passed": ragg.get("n_passed")}
        reproduces = None
        if recorded and _finite(recorded["median_mae"]) and _finite(h["aggregate"].get("median_mae")):
            reproduces = (abs(float(recorded["median_mae"]) - float(h["aggregate"]["median_mae"])) <= 1e-9
                          and recorded["n_passed"] == h["aggregate"].get("n_passed"))
        drec_path = run.dir / f"evaluation_disturbance_v{c.version}.json"
        recorded_dist, reproduces_dist = None, None
        if drec_path.exists():
            drep = json.loads(drec_path.read_text())
            dsuite, dagg = drep.get("suite"), drep.get("aggregate", {})
            recorded_dist = {"suite": dsuite, "median_post_disturbance_mae": dagg.get("median_post_disturbance_mae")}
            fresh_d = cand_scores[c.id].get(dsuite or "")
            if fresh_d and _finite(recorded_dist["median_post_disturbance_mae"]):
                fv = fresh_d["aggregate"].get("median_post_disturbance_mae")
                reproduces_dist = _finite(fv) and abs(float(fv) - float(recorded_dist["median_post_disturbance_mae"])) <= 1e-9
        out["candidates"].append({
            "recorded_disturbance": recorded_dist, "fresh_reproduces_recorded_disturbance": reproduces_dist,
            "candidate_id": c.id, "version": c.version, "sha256": c.sha256, "model_id": c.model_id,
            "parent_id": c.parent_id, "status": status.get(c.id, {}).get("status"),
            "kind": status.get(c.id, {}).get("submission_kind"),
            "fresh_g2": h["gate_passed"], "fresh_heldout_passed": h["aggregate"].get("n_passed"),
            "fresh_median_mae": h["aggregate"].get("median_mae"),
            "recorded_heldout": recorded, "fresh_reproduces_recorded": reproduces,
            "fresh_post_median_mae": {f: cand_scores[c.id][f"disturbance:{f}"]["aggregate"]
                                      .get("median_post_disturbance_mae") for f in fams},
        })

    # ---- costs / timings
    total_calls = _model_call_stats(run)
    v1_ts = reg_events.get(v1.id, {}).get("ts") if v1 else None
    v1_calls = _model_call_stats(run, upto_ts=v1_ts) if v1_ts else None
    v1_wall = (approve_events[v1.id]["ts"] - started_ts) if (v1 and v1.id in approve_events and started_ts) else None
    v1_seq = reg_events.get(v1.id, {}).get("seq") if v1 else None
    exps_to_v1 = (sum(1 for e in events if e.get("kind") == "experiment_result" and e["seq"] < v1_seq)
                  if v1_seq is not None else None)
    out.update({"v1_candidate": v1.id if v1 else None, "final_candidate": final.id if final else None,
                "full_equals_v1": bool(v1 and final and v1.id == final.id),
                "model_calls_total": total_calls, "model_calls_to_v1": v1_calls,
                "wall_s_to_v1": v1_wall, "experiments_to_v1": exps_to_v1})

    # ---- ablation rows per family
    ablation: dict[str, list[dict[str, Any]]] = {}
    for fam in fams:
        rows: list[dict[str, Any]] = []
        for b in baselines:
            rows.append({"variant": BASELINE_LABELS[b], "candidate": f"baseline:{b}",
                         **_variant_metrics(base_scores[b], fam), "model_calls": 0, "cost_usd": 0.0, "wall_s": None,
                         "note": "tuned post hoc on DISTURBANCE_SEEDS (existence proof, not a fair rival)"
                         if b == "slow_pid" else ""})
        if v1 is not None:
            rows.append({"variant": "Muse v1 frozen", "candidate": v1.id, **_variant_metrics(cand_scores[v1.id], fam),
                         "model_calls": (v1_calls or {}).get("calls"), "cost_usd": (v1_calls or {}).get("cost_usd"),
                         "wall_s": v1_wall, "note": "no revision after the disturbance"})
            note = ("no later approved version: Full Praxion = v1 retained" if final.id == v1.id
                    else f"repaired controller {final.id}")
            rows.append({"variant": "Full Praxion", "candidate": final.id,
                         **_variant_metrics(cand_scores[final.id], fam), "model_calls": total_calls.get("calls"),
                         "cost_usd": total_calls.get("cost_usd"), "wall_s": result.get("elapsed_s"), "note": note})
        else:
            for name in ("Muse v1 frozen", "Full Praxion"):
                rows.append({"variant": name, "candidate": None, "note": "no candidate approved in-run"})
        ablation[fam] = rows
    out["ablation"] = ablation

    # ---- gates
    ex = out["experiments"]
    static_ok = [c for c in result.get("candidates") or [] if c.get("static_ok")]
    g1 = ex["distinct_completed"] >= 3 and len(static_ok) >= 1
    gates: dict[str, Any] = {
        "G1": {"passed": g1, "detail": (f"{ex['completed']} completed / {ex['distinct_completed']} distinct "
                                        f"experiments ({ex['tied_to_uncertainty']} name an uncertainty); "
                                        f"{len(static_ok)} statically valid candidate(s)")},
    }
    if v1 is not None:
        h = cand_scores[v1.id]["heldout"]
        gates["G2"] = {"passed": h["gate_passed"], "candidate": v1.id, "detail": "; ".join(h["gate_reasons"][:1])}
    else:
        fresh = ", ".join(f"v{c['version']} {'PASS' if c['fresh_g2'] else 'FAIL'}" for c in out["candidates"]) or "none"
        gates["G2"] = {"passed": False, "candidate": None, "detail": f"no candidate approved in-run (fresh: {fresh})"}

    fam = out["disturbance_family"]
    later = [c for c in cands if v1 is not None and c.version > v1.version]
    g3: dict[str, Any] = {"family": fam, "family_kind": cfg.DISTURBANCE_FAMILIES.get(fam) if fam else None,
                          "attempts": []}
    if fam is None:
        g3.update(passed=None, status="N/A", detail="no disturbance in this run")
    elif v1 is None:
        g3.update(passed=False, status="NOT REACHED", detail="no approved v1")
    elif fam not in fams:
        g3.update(passed=None, status="N/A", detail=f"family {fam!r} not scored")
    else:
        rep_v1 = report_from_slim(cand_scores[v1.id][f"disturbance:{fam}"])
        for c in later:
            cmp = compare_adaptation(rep_v1, report_from_slim(cand_scores[c.id][f"disturbance:{fam}"]))
            g3["attempts"].append({"candidate": c.id, "gate_passed": cmp["gate_passed"], "n_improved": cmp["n_improved"],
                                   "median_reduction": cmp["median_reduction"], "reasons": cmp["reasons"],
                                   "nominal_g2": cand_scores[c.id]["heldout"]["gate_passed"]})
        if not later:
            g3.update(passed=False, status="NOT REACHED",
                      detail=f"no repair candidate (final stage {result.get('stage')}: {out['final_stage_reason']})")
        else:
            # Promotion rule (2026-10-31): G3 = changed-machine criteria (>= GATE3_MIN_PASS scenarios improved
            # >= GATE3_MIN_MAE_REDUCTION, zero hard violations, zero invalid outputs). Nominal G2 after repair
            # and in-run promotion are reported as separate facts, never folded into the verdict.
            best = max(g3["attempts"], key=lambda x: (bool(x["gate_passed"]), x["median_reduction"]))
            promoted = final.id != v1.id
            ok = bool(best["gate_passed"])
            g3.update(passed=ok, status="PASS" if ok else "FAIL", best_candidate=best["candidate"], promoted_in_run=promoted,
                      nominal_g2_after_repair=best["nominal_g2"],
                      detail=(f"{best['candidate']}: {best['n_improved']}/5 improved, median reduction "
                              f"{_fmt_pct(best['median_reduction'])}; nominal G2 after repair "
                              f"{'PASS' if best['nominal_g2'] else 'FAIL'} (reported, not gated); promoted in run: "
                              f"{'yes' if promoted else 'no (promotion rule in force at run time)'}"))
    gates["G3"] = g3

    diags = []
    for p in sorted(run.dir.glob("adaptation_v*.json"), key=lambda p: int(p.stem.split("_v")[-1])):
        d = json.loads(p.read_text())
        diags.append({"file": p.name, "diagnosis_category": d.get("diagnosis_category"),
                      "diagnosis_correct": d.get("diagnosis_correct")})
    gates["diagnosis"] = diags
    out["gates"] = gates
    return out


# =========================================================================== whole benchmark
def build_benchmarks(artifact_root: Path, *, sandbox_mode: str, cache_dir: Path, include_mock: bool = False,
                     plant_seed_override: int | None = None, run_ids: Iterable[str] | None = None,
                     baselines: Iterable[str] = tuple(BASELINE_SPECS), families: Iterable[str] | None = None,
                     progress: Callable[[str], None] | None = None) -> dict[str, Any]:
    if sandbox_mode not in ("docker", "subprocess_dev_only"):
        raise BenchmarkError(f"unknown sandbox mode {sandbox_mode!r}")
    if sandbox_mode == "docker":
        from backend.controller.sandbox import docker_available, ensure_image

        if not docker_available():
            raise BenchmarkError("Docker is not available; pass --sandbox subprocess_dev_only (dev only)")
        ensure_image()
    say = progress or (lambda _m: None)
    cache = ReportCache(Path(cache_dir))
    registry = Registry(artifact_root)
    runs, skipped = discover_runs(Path(artifact_root) / "runs", include_mock=include_mock,
                                  plant_seed_override=plant_seed_override, run_ids=run_ids)
    t0 = time.time()
    rows = []
    for r in runs:
        say(f"run {r.run_id} (plant_seed={r.plant_seed}{', MOCK' if r.is_mock else ''})")
        rows.append(benchmark_run(r, registry=registry, sandbox_mode=sandbox_mode, cache=cache, baselines=baselines,
                                  families=families, progress=say))
    return {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "sandbox_mode": sandbox_mode,
        "include_mock": include_mock,
        "frozen_config": frozen_config(),
        "evaluator_fingerprint": cache.fingerprint,
        "baselines": list(baselines),
        "families": list(families or cfg.DISTURBANCE_FAMILIES),
        "runs": rows,
        "skipped": skipped,
        "summary": summarize(rows),
        "cache": {"hits": cache.hits, "misses": cache.misses, "dir": str(cache_dir)},
        "scoring_wall_s": round(time.time() - t0, 1),
    }


def summarize(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    groups: dict[str, list[dict[str, Any]]] = {}
    for r in rows:
        groups.setdefault(str(r.get("prompt_version")), []).append(r)
    out = []
    for pv, rs in sorted(groups.items()):
        valid = [r for r in rs if not r.get("aborted")]

        def rate(g: str, rows_: list[dict[str, Any]] = valid, n: int = len(rs)) -> str:
            return f"{sum(1 for r in rows_ if r['gates'][g]['passed'])}/{n}"

        out.append({
            "prompt_version": pv, "runs": len(rs), "aborted": len(rs) - len(valid),
            "mock_runs": sum(1 for r in rs if r.get("mock")),
            "G1": rate("G1"), "G2": rate("G2"), "G3": rate("G3"),
            "G3_not_reached": sum(1 for r in valid if r["gates"]["G3"].get("status") == "NOT REACHED"),
            "median_experiments_to_v1": _median(r.get("experiments_to_v1") for r in valid),
            "median_cost_usd": _median((r.get("model_calls_total") or {}).get("cost_usd") for r in valid),
            "median_wall_s": _median(r.get("elapsed_s") for r in valid),
        })
    return out


# =========================================================================== markdown
def _fmt(x: Any, nd: int = 4) -> str:
    if x is None:
        return "—"
    if isinstance(x, bool):
        return "yes" if x else "no"
    if isinstance(x, int | float):
        return f"{x:.{nd}f}" if _finite(x) else "—"
    return str(x)


def _fmt_pct(x: Any) -> str:
    return f"{100 * float(x):.1f}%" if _finite(x) else "—"


def _pf(p: Any) -> str:
    return "PASS" if p is True else ("FAIL" if p is False else "N/A")


def render_markdown(data: dict[str, Any], command: str) -> str:
    L: list[str] = []
    mock_any = any(r.get("mock") for r in data["runs"])
    L += ["# Praxion benchmarks", "",
          "<!-- GENERATED by scripts/run_evaluation.py. Do not edit by hand; regenerate instead. -->", "",
          f"- Generated: {data['generated_at']}",
          f"- Command: `{command}`",
          f"- Fresh-scoring sandbox: `{data['sandbox_mode']}`"
          + (" (DEV ONLY: model-authored code ran in a local subprocess, not Docker)"
             if data["sandbox_mode"] != "docker" else ""),
          f"- Evaluator fingerprint (frozen config + scoring code hash): `{data['evaluator_fingerprint']}`",
          (f"- Cache: {data['cache']['hits']} hits, {data['cache']['misses']} fresh scorings; "
          f"scoring wall time {data['scoring_wall_s']} s"), ""]
    if mock_any:
        L += [("> **MOCK RUNS INCLUDED.** Rows labeled MOCK come from the CI mock agent (`MOCK-NOT-MUSE`). "
              "They exercise plumbing only and are NOT results."), ""]
    L += ["Every number below is regenerated from the stored run bundles: candidate sources are re-hashed, then "
          "scored fresh on the frozen held-out and disturbance scenarios from `backend/evaluation/config.py`. "
          "The stored in-run reports are only used to check that fresh scores reproduce them. "
          + ("Mock runs are included and labeled MOCK." if data["include_mock"]
             else "Mock runs are excluded."), "",
          "## Frozen configuration", "", "| key | value |", "|---|---|"]
    for k, v in data["frozen_config"].items():
        L.append(f"| `{k}` | `{json.dumps(v)}` |")
    L.append("")

    # ---------- cross-run summary
    L += ["## Cross-run summary (per protocol version)", "",
          ("G3 counts a run as not passed when it never reached repair (stopped or failed earlier); "
          "those runs are counted separately in *G3 not reached*."), "",
          ("| prompt version | runs | G1 | G2 | G3 | G3 not reached | median experiments to v1 | "
          "median cost USD | median wall s |"), "|---|---:|---:|---:|---:|---:|---:|---:|---:|"]
    for s in data["summary"]:
        mock = f" ({s['mock_runs']} MOCK)" if s["mock_runs"] else ""
        L.append(f"| {s['prompt_version']}{mock} | {s['runs']} | {s['G1']} | {s['G2']} | {s['G3']} | "
                 f"{s['G3_not_reached']} | {_fmt(s['median_experiments_to_v1'], 1)} | "
                 f"{_fmt(s['median_cost_usd'], 3)} | {_fmt(s['median_wall_s'], 1)} |")
    if not data["summary"]:
        L.append("| — | 0 | — | — | — | — | — | — | — |")
    L.append("")

    # ---------- every run (failures included)
    L += ["## Every run", "",
          ("| run | label | model | prompt | plant seed | final stage | G1 | G2 | G3 | diagnosis | experiments to v1 | "
          "model calls | cost USD | wall s |"), "|---|---|---|---|---:|---|---|---|---|---|---:|---:|---:|---:|"]
    for r in data["runs"]:
        label = "MOCK" if r.get("mock") else "live"
        if r.get("aborted"):
            L.append(f"| `{r['run_id']}` | {label} | {r.get('model_id')} | {r.get('prompt_version')} | "
                     f"{r.get('plant_seed')} | {r.get('final_stage')} | ABORTED: {r['aborted']} | | | | | | | |")
            continue
        g = r["gates"]
        diag = ", ".join(f"{d['diagnosis_category']}={'correct' if d['diagnosis_correct'] else 'wrong'}"
                         for d in g["diagnosis"]) or "—"
        mc = r.get("model_calls_total") or {}
        L.append(f"| `{r['run_id']}` | {label} | {r.get('model_id')} | {r.get('prompt_version')} | {r['plant_seed']} | "
                 f"{r['final_stage']} | {_pf(g['G1']['passed'])} | {_pf(g['G2']['passed'])} | "
                 f"{g['G3'].get('status') if g['G3'].get('status') in ('NOT REACHED', 'N/A') else _pf(g['G3']['passed'])}"
                 f" | {diag} | {_fmt(r.get('experiments_to_v1'), 0)} | {_fmt(mc.get('calls'), 0)} | "
                 f"{_fmt(mc.get('cost_usd'), 3)} | {_fmt(r.get('elapsed_s'), 1)} |")
    for s in data["skipped"]:
        L.append(f"| `{s['run_id']}` | skipped | | | | | {s['reason']} | | | | | | | |")
    L.append("")

    # ---------- per-run detail
    for r in data["runs"]:
        tag = " — MOCK (plumbing only, not a result)" if r.get("mock") else ""
        L += [f"## Run `{r['run_id']}`{tag}", "",
              (f"- Model `{r.get('model_id')}`, prompt `{r.get('prompt_version')}` (`{r.get('prompt_hash')}`), "
              f"agent mode `{r.get('agent_mode')}`, recorded sandbox `{r.get('recorded_sandbox_mode')}`"),
              f"- Plant seed {r['plant_seed']} (from {r['plant_seed_source']}); disturbance used in-run: "
              f"`{r.get('disturbance_family')}`; final stage `{r.get('final_stage')}`"
              + (f" ({r['final_stage_reason']})" if r.get("final_stage_reason") else ""), ""]
        if r.get("aborted"):
            L += [f"**ABORTED:** {r['aborted']}", ""]
            continue
        g = r["gates"]
        L += ["### Gates", "", "| gate | result | detail |", "|---|---|---|",
              f"| G1 discovery | {_pf(g['G1']['passed'])} | {g['G1']['detail']} |",
              (f"| G2 performance (fresh held-out of v1) | {_pf(g['G2']['passed'])} | "
              f"{g['G2'].get('candidate') or '—'}: {g['G2']['detail']} |"),
              (f"| G3 self-repair (`{g['G3'].get('family')}`, {g['G3'].get('family_kind')}) | "
              f"{g['G3'].get('status')} | {g['G3'].get('detail')} |")]
        if g["diagnosis"]:
            for d in g["diagnosis"]:
                L.append(f"| diagnosis ({d['file']}) | {'correct' if d['diagnosis_correct'] else 'WRONG'} | "
                         f"category `{d['diagnosis_category']}` vs hidden family `{g['G3'].get('family')}` |")
        else:
            L.append("| diagnosis | N/A | no adaptation attempt recorded |")
        L.append("")
        for a in g["G3"].get("attempts", []):
            L.append(f"- Repair attempt `{a['candidate']}`: {'; '.join(a['reasons'])}; nominal G2 "
                     f"{_pf(a['nominal_g2'])}")
        if g["G3"].get("attempts"):
            L.append("")

        L += ["### Candidates (fresh scores)", "",
              "| candidate | kind | in-run status | sha256 | fresh G2 | held-out passed | median MAE | "
              "reproduces recorded (held-out / disturbance) | "
              + " | ".join(f"post MAE {f}" for f in data["families"]) + " |",
              "|---|---|---|---|---|---:|---:|---|" + "---:|" * len(data["families"])]
        for c in r["candidates"]:
            L.append(f"| `{c['candidate_id']}` | {c['kind']} | {c['status']} | `{c['sha256'][:12]}` | "
                     f"{_pf(c['fresh_g2'])} | {_fmt(c['fresh_heldout_passed'], 0)}/10 | {_fmt(c['fresh_median_mae'])} | "
                     f"{_fmt(c['fresh_reproduces_recorded'])} / {_fmt(c['fresh_reproduces_recorded_disturbance'])} | "
                     + " | ".join(_fmt(c["fresh_post_median_mae"][f]) for f in data["families"]) + " |")
        L.append("")
        if any(c["fresh_reproduces_recorded"] is False or c["fresh_reproduces_recorded_disturbance"] is False
               for c in r["candidates"]):
            L += [("> **Fresh scores differ from the in-run reports for at least one candidate.** The candidate bytes "
                   "are hash-verified, so the difference comes from the evaluator: the frozen config or scoring code "
                   "changed after this run was recorded. The fresh numbers (current frozen config) are the ones "
                   "reported here; the in-run reports remain in the bundle."), ""]

        L += ["### Ablation (same plant seed, same frozen scenarios)", "",
              ("Nominal = 10 held-out episodes scored after settling. Post = 5 disturbance episodes, MAE over "
              "t >= disturbance time, in-band scored from disturbance + settle. Adaptation latency = median seconds "
              "from the disturbance to the start of the first 10 s sustained in-band run (recovered episodes only); as "
              "frozen in `metrics.py` it is 0 s when the level is still in band right after the change, even if the "
              "loop destabilises later, so read it together with post in-band. Overrides and hard "
              "violations are shown nominal / post. Model calls and cost: v1 frozen counts calls up to v1's "
              "registration; Full Praxion counts the whole run. Wall time: v1 = start to v1 approval; "
              "Full = whole run."), ""]
        for fam, rows in r["ablation"].items():
            kind = data["frozen_config"]["DISTURBANCE_FAMILIES"].get(fam)
            used = " — **family used in this run**" if fam == r.get("disturbance_family") else ""
            L += [f"#### `{fam}` ({kind}){used}", "",
                  ("| variant | candidate | nominal median MAE | nominal in-band | nominal energy | post median MAE | "
                  "post in-band | adaptation latency s (recovered) | overrides | hard violations | model calls | "
                  "est. cost USD | wall s | note |"),
                  "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|"]
            for row in rows:
                if row.get("candidate") is None:
                    L.append(f"| {row['variant']} | — | | | | | | | | | | | | {row['note']} |")
                    continue
                cand = row["candidate"] if row["candidate"].startswith("baseline:") else f"`{row['candidate']}`"
                L.append(
                    f"| {row['variant']} | {cand} | {_fmt(row['nominal_median_mae'])} | "
                    f"{_fmt(row['nominal_in_band'], 3)} | {_fmt(row['nominal_energy'], 2)} | "
                    f"{_fmt(row['post_median_mae'])} | {_fmt(row['post_in_band'], 3)} | "
                    f"{_fmt(row['adaptation_latency_s'], 1)} ({row['recovered']}) | "
                    f"{row['overrides_nominal']} / {row['overrides_post']} | "
                    f"{row['hard_violations_nominal']} / {row['hard_violations_post']} | "
                    f"{_fmt(row['model_calls'], 0)} | {_fmt(row['cost_usd'], 3)} | {_fmt(row['wall_s'], 1)} | "
                    f"{row['note']} |")
            L.append("")

    L += ["## How to reproduce", "",
          "```bash",
          "uv sync",
          "uv run python scripts/run_evaluation.py --sandbox docker        # regenerates this file",
          "uv run python scripts/audit_run.py <run_id>                     # independent per-run audit",
          "uv run python scripts/export_artifacts.py <run_id>              # zip bundle for judges",
          "```", "",
          ("- Raw numbers: `artifacts/benchmarks/latest.json`. Fresh reports are cached in "
          "`artifacts/benchmarks/cache/<sha256>-<suite>-<plant_seed>.json`; delete that directory to force a full "
          "re-score. A cache entry is reused only if the evaluator fingerprint and sandbox mode match."),
          ("- Scenario seeds, windows and thresholds are frozen in `backend/evaluation/config.py`; nothing in this "
          "report tunes them. The plant seed for each run is read from the trusted audit entries of its stored "
          "evaluation report."),
          ("- Baselines are transparent and never shown to the model. The *slow PID* tuning was chosen by a small "
          "manual sweep on the disturbance scenarios; it is an existence proof that the dynamics disturbance is "
          "repairable, not a fair competitor. If a baseline beats Praxion, that is the result."),
          ""]
    return "\n".join(L)


def write_outputs(data: dict[str, Any], *, markdown_path: Path, json_path: Path, command: str) -> None:
    markdown_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.parent.mkdir(parents=True, exist_ok=True)
    markdown_path.write_text(render_markdown(data, command))
    json_path.write_text(json.dumps(data, indent=1, default=str))
