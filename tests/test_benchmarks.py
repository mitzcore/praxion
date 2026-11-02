"""backend/evaluation/benchmarks.py: real fresh scoring on the frozen scenarios (subprocess sandbox), markdown
sections, MOCK labeling, hash-abort, and the source-hash cache. Baselines restricted to on/off + slow PID to
keep the test fast; scenario lists are frozen and NOT reduced."""
from __future__ import annotations

import json
from pathlib import Path

from backend.evaluation import benchmarks as bm
from backend.evaluation.config import DISTURBANCE_FAMILIES
from tests.test_audit import build_run

BASELINES = ("fixed_onoff", "slow_pid", "relay_pi", "relay_pi_retuned")


def _build(tmp_path: Path, **kw) -> tuple[Path, Path]:
    art = tmp_path / "artifacts"
    run_dir = build_run(art, **kw)
    return art, run_dir


def _bench(art: Path, cache: Path, **kw) -> dict:
    return bm.build_benchmarks(art, sandbox_mode="subprocess_dev_only", cache_dir=cache, include_mock=True,
                               plant_seed_override=7, baselines=BASELINES, **kw)


def test_mock_runs_excluded_by_default_and_seed_required(tmp_path: Path) -> None:
    art, run_dir = _build(tmp_path)
    runs, skipped = bm.discover_runs(art / "runs", include_mock=False)
    assert runs == [] and "mock" in skipped[0]["reason"]
    runs, skipped = bm.discover_runs(art / "runs", include_mock=True)  # no evaluation report, no override
    assert runs == [] and "plant seed" in skipped[0]["reason"]
    (run_dir / "evaluation_v1.json").write_text(json.dumps({"comparison": {"audit": [{"plant_seed": 11}]}}))
    runs, _ = bm.discover_runs(art / "runs", include_mock=True)
    assert runs[0].plant_seed == 11 and runs[0].is_mock


def test_non_tank_profiles_are_skipped(tmp_path: Path) -> None:
    art, run_dir = _build(tmp_path)
    # Older bundle: profile only visible through the evaluator audit's hidden-parameter kind.
    (run_dir / "evaluation_v1.json").write_text(json.dumps(
        {"comparison": {"audit": [{"plant_seed": 11, "hidden_params": {"kind": "thermal_twin_fopdt"}}]}}))
    runs, skipped = bm.discover_runs(art / "runs", include_mock=True)
    assert runs == [] and "tclab_sim" in skipped[0]["reason"] and "tank" in skipped[0]["reason"]
    # Newer bundle: profile recorded in result.json wins.
    rp = run_dir / "result.json"
    res = json.loads(rp.read_text()); res["profile"] = {"name": "tclab"}; rp.write_text(json.dumps(res))
    _, skipped = bm.discover_runs(art / "runs", include_mock=True)
    assert "'tclab'" in skipped[0]["reason"]
    # Tank audits (no kind) and tank profiles are kept.
    res["profile"] = {"name": "tank"}; rp.write_text(json.dumps(res))
    runs, skipped = bm.discover_runs(art / "runs", include_mock=True)
    assert len(runs) == 1 and skipped == []


def test_hash_failure_aborts_run_rows(tmp_path: Path) -> None:
    art, run_dir = _build(tmp_path)
    p = run_dir / "controller_v1.py"
    p.write_bytes(p.read_bytes() + b"# tampered\n")
    data = _bench(art, tmp_path / "cache")
    assert data["runs"][0]["aborted"] and "hash" in data["runs"][0]["aborted"]
    assert data["cache"]["misses"] == 0  # nothing scored
    assert "ABORTED" in bm.render_markdown(data, "test")


def test_benchmark_markdown_and_cache(tmp_path: Path) -> None:
    art, _ = _build(tmp_path, sources=("pi_controller.py", "p_controller.py"), statuses=("approved", "failed_gate"))
    cache = tmp_path / "cache"
    md, js = tmp_path / "BENCHMARKS.md", tmp_path / "latest.json"

    first = _bench(art, cache)
    n_suites = 1 + len(DISTURBANCE_FAMILIES)
    # 2 candidates + on/off + slow PID + relay nominal: every suite; relay re-tuned: heldout + its family, per family
    expected_misses = (2 + 3) * n_suites + 2 * len(DISTURBANCE_FAMILIES)
    assert first["cache"] == {"hits": 0, "misses": expected_misses, "dir": str(cache)}
    bm.write_outputs(first, markdown_path=md, json_path=js, command="pytest")
    text = md.read_text()
    for section in ("# Praxion benchmarks", "## Frozen configuration", "## Cross-run summary (per protocol version)",
                    "## Every run", "### Gates", "### Candidates (fresh scores)",
                    "### Ablation (same plant seed, same frozen scenarios)", "## How to reproduce",
                    "#### `actuator_lag` (dynamics) — **family used in this run**"):
        assert section in text, section
    for variant in ("fixed on/off", "slow PID", "relay auto-tuned PI (nominal)", "relay PI re-tuned after change",
                    "Muse v1 frozen", "Full Praxion"):
        assert f"| {variant} |" in text, variant
    assert "## Praxion vs the classical self-tuner" in text
    bt = first["runs"][0]["baseline_tuning"]
    assert bt["relay_pi"]["retuned"] is False and set(bt["relay_pi_retuned"]) == set(DISTURBANCE_FAMILIES)
    assert bt["relay_pi_retuned"]["actuator_lag"]["retuned"] is True
    assert "MOCK RUNS INCLUDED" in text and "| MOCK |" in text
    assert "DEV ONLY" in text  # subprocess sandbox is labeled
    assert "Full Praxion = v1 retained" in text  # v2 failed its gate, so the full system keeps v1

    run = first["runs"][0]
    assert run["gates"]["G1"]["passed"] is True
    assert run["gates"]["G3"]["family"] == "actuator_lag"
    # Promotion rule (2026-11-01): G3 is judged on changed-machine criteria; the synthetic v2 meets them even
    # though the recorded run did not promote it, and the benchmark reports both facts.
    g3 = run["gates"]["G3"]
    assert len(g3["attempts"]) == 1 and g3["status"] == ("PASS" if g3["attempts"][0]["gate_passed"] else "FAIL")
    assert g3["promoted_in_run"] is False and "promoted in run: no" in g3["detail"]
    assert run["gates"]["diagnosis"][0]["diagnosis_correct"] is False
    assert set(run["ablation"]) == set(DISTURBANCE_FAMILIES)
    assert json.loads(js.read_text())["runs"][0]["run_id"] == run["run_id"]

    second = _bench(art, cache)
    assert second["cache"]["misses"] == 0 and second["cache"]["hits"] == first["cache"]["misses"]
    assert second["runs"][0]["ablation"] == run["ablation"]
    assert second["runs"][0]["gates"] == run["gates"]

    # A different sandbox mode must not reuse sandboxed-candidate entries (baselines are trusted, so they still hit).
    c = bm.ReportCache(cache)
    sha = run["candidates"][0]["sha256"]
    assert c.get(sha, "heldout", 7, "docker") is None
    assert c.get(sha, "heldout", 7, "subprocess_dev_only") is not None
