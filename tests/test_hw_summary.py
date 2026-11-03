"""scripts/hw_summary.py: table rows from real + synthetic bundles, sign test, Clopper–Pearson."""
from __future__ import annotations

import importlib.util
import json
import shutil
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location("hw_summary", ROOT / "scripts" / "hw_summary.py")
hs = importlib.util.module_from_spec(_spec)
sys.modules["hw_summary"] = hs
_spec.loader.exec_module(hs)

HW1 = ROOT / "artifacts" / "runs" / "hw1-20261102-234915-81765d"
HW2 = ROOT / "artifacts" / "runs" / "hw2-20261103-074537-698ba8"
PROFILE = {"name": "tclab", "y_scale": 60.0, "y_offset": 15.0, "target": 0.5}


def test_sign_test_exact():
    assert hs.sign_test_one_sided(4, 4) == pytest.approx(0.0625)
    assert hs.sign_test_one_sided(5, 6) == pytest.approx(7 / 64)
    assert hs.sign_test_one_sided(0, 3) == pytest.approx(1.0)


def test_clopper_pearson_known_cases():
    lo, hi = hs.clopper_pearson(4, 4)
    assert lo == pytest.approx(0.025 ** 0.25, abs=1e-6) and hi == 1.0
    lo, hi = hs.clopper_pearson(0, 4)
    assert lo == 0.0 and hi == pytest.approx(1 - 0.025 ** 0.25, abs=1e-6)
    lo, hi = hs.clopper_pearson(5, 10)  # textbook: [0.1871, 0.8129]
    assert lo == pytest.approx(0.18709, abs=1e-4) and hi == pytest.approx(0.81291, abs=1e-4)


def _write_synthetic(d: Path, name: str, mae_v1: float, mae_v2: float, ib1: float, ib2: float,
                     operator_run: bool = False) -> None:
    run_id = f"{name}-20261104-010000-abcdef"
    b = d / run_id
    b.mkdir(parents=True)
    (b / "result.json").write_text(json.dumps({
        "run_id": run_id, "stage": "COMPLETE", "model_id": "muse-spark-1.3", "profile": PROFILE, "elapsed_s": 6000.0,
        "monitoring": {"disturbance_family": "pump_derate", "disturbance_at_t": 600.0},
        "stage_history": [{"from": "EVALUATING", "to": "COMPLETE", "candidate_id": f"{run_id}-v2", "reason": "v2 promoted"}]}))
    events = [
        {"kind": "run_started", "ts": 1793754000.0},
        {"kind": "monitoring_result", "degraded": True, "degraded_at_t": 645.0},
        {"kind": "adaptation_result", "diagnosis_correct": True, "nominal_gate_passed": True},
    ]
    if operator_run:
        events.insert(1, {"kind": "operator_disturbance_applied", "t": 600.0})
    (b / "event_log.jsonl").write_text("\n".join(json.dumps(e) for e in events) + "\n")
    (b / "evaluation_v1.json").write_text(json.dumps({"gate_passed": True, "aggregate": {
        "n_passed": 8.0, "n_episodes": 10.0, "median_mae": 0.01}}))
    (b / "evaluation_disturbance_v1.json").write_text(json.dumps({"aggregate": {"median_post_disturbance_mae": 0.10}}))
    (b / "evaluation_disturbance_v2.json").write_text(json.dumps({"aggregate": {"median_post_disturbance_mae": 0.02}}))
    (b / "adaptation_v2.json").write_text(json.dumps({"comparison": {"median_reduction": 0.8}, "diagnosis_category":
                                                       "inflow_reduced", "diagnosis_correct": True, "nominal_gate": True}))
    steps = [{"t": float(t), "y": 0.5 if t < 600 else 0.4} for t in range(0, 1200, 10)]
    (b / "monitoring.json").write_text(json.dumps({"degraded_at_t": 645.0, "trace": {"steps": steps, "disturbance_at": 600.0}}))
    (b / "model_calls.jsonl").write_text("\n".join(json.dumps({"ok": True, "cost_usd": 0.25}) for _ in range(4)) + "\n")
    (b / "board_verification.json").write_text(json.dumps({
        "trials": [{"label": "v1", "post_mae": mae_v1, "post_in_band": ib1}, {"label": "v2", "post_mae": mae_v2,
                                                                                 "post_in_band": ib2}],
        "order": ["v1", "v2"], "pre_s": 300, "post_s": 900,
        "disturbance": {"family": "pump_derate", "magnitude": 0.35, "applied_by": "trusted_actuator"},
        "comparison": {"post_mae_v1": mae_v1, "post_mae_v2": mae_v2, "reduction": 1 - mae_v2 / mae_v1,
                       "in_band_v1": ib1, "in_band_v2": ib2}}))


def _copy_real(dst: Path) -> None:
    for src in (HW1, HW2):
        shutil.copytree(src, dst / src.name, ignore=shutil.ignore_patterns("agent_view_snapshots", "controller_*"))


def test_synthetic_bundle_row_and_stats(tmp_path):
    root = tmp_path / "runs"
    _write_synthetic(root, "hwsyn", mae_v1=0.08, mae_v2=0.03, ib1=0.2, ib2=0.6)
    runs = hs.collect(root, "hw*")
    assert len(runs) == 1
    r = runs[0]
    assert r["disturbance"] == "pump_derate (trusted, m=0.35)" and not r["board"]["mismatch"]
    assert r["detection_latency_s"] == 45.0
    assert r["v1_min_after_c"] == pytest.approx(0.4 * 60 + 15)
    assert r["twin_v1_c"] == pytest.approx(6.0) and r["twin_v2_c"] == pytest.approx(1.2)
    assert r["board"]["v1_c"] == pytest.approx(4.8) and r["board"]["v2_c"] == pytest.approx(1.8)
    assert r["cost_usd"] == pytest.approx(1.0) and r["repair_promoted"]
    agg = hs.aggregate(runs)
    assert agg["n_success"] == 1 and agg["sign_k"] == 1 and agg["sign_p"] == pytest.approx(0.5)


def test_mismatched_board_change_excluded(tmp_path):
    root = tmp_path / "runs"
    # fan (operator) run later verified on the board with the trusted derate: different change
    _write_synthetic(root, "hwmis", mae_v1=0.08, mae_v2=0.03, ib1=0.2, ib2=0.6, operator_run=True)
    _write_synthetic(root, "hwok", mae_v1=0.08, mae_v2=0.03, ib1=0.2, ib2=0.6)
    runs = hs.collect(root, "hw*")
    mis = next(r for r in runs if r["run_id"].startswith("hwmis"))
    assert mis["disturbance"] == "operator (fan)"  # the run's own change, not the board file's
    assert mis["board"]["mismatch"] and mis["board"]["change"] == "pump_derate/trusted_actuator"
    agg = hs.aggregate(runs)
    assert agg["n_verified"] == 1 and [r["run_id"][:4] for r in agg["verified"]] == ["hwok"]
    assert agg["sign_k"] == 1 and agg["sign_n"] == 1 and agg["cp"] == pytest.approx((0.025, 1.0))
    out = tmp_path / "H.md"
    hs.main(["--root", str(root), "--out", str(out), "--no-figure"])
    md = out.read_text()
    row = next(ln for ln in md.splitlines() if ln.startswith("| `hwmis") and ln.count("|") == 13)
    assert "4.80 → 1.80 (62%) mismatch (different change: pump_derate/trusted_actuator), excluded" in row
    assert not any(ln.startswith("| `hwmis") and ln.count("|") == 9 for ln in md.splitlines())  # not in paired list
    assert "| board-verified improvement (board reduction > 0 and in-band v2 > v1) | 1 / 1 |" in md


def test_fake_board_excluded_from_evidence(tmp_path):
    root = tmp_path / "runs"
    _write_synthetic(root, "hwfake", mae_v1=0.08, mae_v2=0.03, ib1=0.2, ib2=0.6)
    bvp = next(root.glob("hwfake-*")) / "board_verification.json"
    bv = json.loads(bvp.read_text())
    bv["fake_board"] = True
    bvp.write_text(json.dumps(bv))
    agg = hs.aggregate(hs.collect(root, "hw*"))
    assert agg["n_verified"] == 0 and agg["sign_p"] is None


@pytest.mark.skipif(not (HW1.is_dir() and HW2.is_dir()), reason="real hardware bundles not present")
def test_real_bundles_plus_synthetic(tmp_path):
    root = tmp_path / "runs"
    root.mkdir()
    _copy_real(root)
    _write_synthetic(root, "hwsyn", mae_v1=0.08, mae_v2=0.03, ib1=0.2, ib2=0.6)
    (root / "tank-run").mkdir()  # non-hardware bundles are ignored by the glob / profile filter
    out = tmp_path / "HARDWARE_RESULTS.md"
    assert hs.main(["--root", str(root), "--out", str(out), "--png", str(tmp_path / "img" / "hw.png")]) == 0
    md = out.read_text()
    rows = [ln for ln in md.splitlines() if ln.startswith("| `hw")]
    per_run = [ln for ln in rows if ln.count("|") == 13]
    assert len(per_run) == 3
    hw1, hw2, syn = per_run
    assert "FAILED" in hw1 and "no (0/10, 2.18)" in hw1 and "not reached" in hw1
    assert "operator (fan)" in hw2 and "yes (9/10, 0.72)" in hw2 and "| 66 |" in hw2
    assert "7.50 → 1.09 (86%)" in hw2 and "| — | 33.7 |" in hw2
    assert "## Twin fidelity under the board protocol" in text
    assert "pump_derate (trusted, m=0.35)" in syn and "4.80 → 1.80 (62%)" in syn and "6.00 → 1.20 (80%)" in syn
    assert "| board-verified improvement (board reduction > 0 and in-band v2 > v1) | 1 / 1 |" in md
    assert "p = P(X ≥ 1 | n=1, ½) = 0.5000" in md
    assert "[0.025, 1.000]" in md
    pair = [ln for ln in rows if ln.count("|") == 9]
    assert len(pair) == 1 and pair[0].endswith("| yes |")
    assert any((tmp_path / "img").iterdir())
    first = md
    hs.main(["--root", str(root), "--out", str(out), "--png", str(tmp_path / "img" / "hw.png")])
    assert out.read_text() == first  # idempotent


@pytest.mark.skipif(not (HW1.is_dir() and HW2.is_dir()), reason="real hardware bundles not present")
def test_only_real_bundles_reads_not_yet_measured(tmp_path):
    root = tmp_path / "runs"
    root.mkdir()
    _copy_real(root)
    out = tmp_path / "H.md"
    hs.main(["--root", str(root), "--out", str(out), "--no-figure"])
    md = out.read_text()
    assert "not yet measured (0 board-verified runs)" in md
    assert "Not yet measured: no bundle contains a matching, real-board `board_verification.json`." in md
