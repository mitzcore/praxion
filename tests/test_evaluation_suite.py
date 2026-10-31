"""Independent evaluator suites (backend/evaluation/suite.py)."""
from __future__ import annotations

import inspect
import json

import pytest

from backend.agent.view import find_leaks
from backend.controller.runtime import run_episode as _run_episode
from backend.evaluation.baselines import ConstantController, OnOffController, PIDController
from backend.evaluation.config import DISTURBANCE_SEEDS, GATE2_MIN_PASS, HELDOUT_SEEDS
from backend.evaluation.report import EvaluationReport
from backend.evaluation.suite import evaluate_disturbance, evaluate_heldout, report_summary

pytestmark = pytest.mark.skipif(
    "scenario" not in inspect.signature(_run_episode).parameters,
    reason="runtime.run_episode does not accept `scenario` yet (plant_seed/scenario split not landed)",
)

# One fixed machine; HELDOUT_SEEDS / DISTURBANCE_SEEDS are scenarios on it.
PLANT_SEED = 5


class CountingFactory:
    """Factory that records how many controllers it built and whether they were closed."""

    def __init__(self, make):
        self.make, self.built = make, []

    def __call__(self):
        c = self.make()
        orig_close = c.close
        c.closed = False

        def close():
            c.closed = True
            orig_close()

        c.close = close
        self.built.append(c)
        return c


@pytest.fixture(scope="module")
def pid_factory():
    return CountingFactory(PIDController)


@pytest.fixture(scope="module")
def pid_heldout(pid_factory) -> EvaluationReport:
    return evaluate_heldout(pid_factory, candidate_id="cand_pid", plant_seed=PLANT_SEED)


@pytest.fixture(scope="module")
def const_heldout() -> EvaluationReport:
    return evaluate_heldout(lambda: ConstantController(0.5), candidate_id="cand_const", plant_seed=PLANT_SEED)


@pytest.fixture(scope="module")
def onoff_heldout() -> EvaluationReport:
    return evaluate_heldout(OnOffController, candidate_id="cand_onoff", plant_seed=PLANT_SEED)


@pytest.fixture(scope="module")
def pid_dist() -> EvaluationReport:
    return evaluate_disturbance(PIDController, "pump_derate", candidate_id="cand_pid", plant_seed=PLANT_SEED)


def test_factory_called_once_and_closed(pid_heldout, pid_factory):
    assert len(pid_factory.built) == 1
    assert pid_factory.built[0].closed


def test_pid_passes_g2(pid_heldout):
    r = pid_heldout
    assert r.suite == "heldout" and r.gate_name == "G2"
    assert [e.index for e in r.episodes] == list(range(len(HELDOUT_SEEDS)))
    assert [e.seed for e in r.episodes] == HELDOUT_SEEDS
    print("\nPID G2:", {k: r.aggregate[k] for k in ("n_passed", "median_mae", "mean_in_band_fraction")})
    assert r.aggregate["n_passed"] >= GATE2_MIN_PASS
    assert r.gate_passed


def test_constant_fails_g2(const_heldout):
    assert not const_heldout.gate_passed
    assert any(e.fail_reasons for e in const_heldout.episodes)
    assert all(not e.passed for e in const_heldout.episodes if e.fail_reasons)


def test_onoff_reported(onoff_heldout):
    a = onoff_heldout.aggregate
    print("\nOn/off G2:", onoff_heldout.gate_passed,
          {k: a[k] for k in ("n_passed", "median_mae", "mean_in_band_fraction", "total_overrides")})
    assert len(onoff_heldout.episodes) == len(HELDOUT_SEEDS)


def test_heldout_comparison_and_aggregate(pid_heldout):
    r = pid_heldout
    for key in ("n_passed", "median_mae", "mean_in_band_fraction", "median_actuation_energy",
                "total_overrides", "total_hard_violations", "total_invalid_outputs",
                "baseline_pid_median_mae", "baseline_onoff_median_mae"):
        assert key in r.aggregate
    for name in ("baseline_pid", "baseline_onoff"):
        assert len(r.comparison[name]["per_seed"]) == len(HELDOUT_SEEDS)
    # Candidate is a PID too: identical same-seed results.
    assert r.aggregate["median_mae"] == pytest.approx(r.aggregate["baseline_pid_median_mae"])
    audit = r.comparison["audit"]
    assert len(audit) == 3 * len(HELDOUT_SEEDS)
    assert audit[0]["plant_seed"] == PLANT_SEED and audit[0]["scenario"] == HELDOUT_SEEDS[0]
    assert audit[0]["hidden_params"]["seed"] == PLANT_SEED
    assert audit[0]["hidden_params"]["scenario"] == HELDOUT_SEEDS[0]
    # Same machine in every episode: physical parameters identical across scenarios.
    assert len({a["hidden_params"]["tank_area"] for a in audit}) == 1


def test_disturbance_report(pid_dist):
    r = pid_dist
    assert r.suite == "disturbance:pump_derate" and r.gate_name == "G3-candidate"
    assert len(r.episodes) == len(DISTURBANCE_SEEDS) == 5
    assert all(e.passed for e in r.episodes) and r.gate_passed
    assert all(e.disturbance_family == "pump_derate" for e in r.episodes)
    assert [e.seed for e in r.episodes] == DISTURBANCE_SEEDS
    assert all(e.trace.meta["seed"] == PLANT_SEED for e in r.episodes)
    pdm = r.comparison["post_disturbance_mae"]
    assert set(pdm) == {str(e.index) for e in r.episodes}
    assert all(v >= 0 for v in pdm.values())
    assert "median_post_disturbance_mae" in r.aggregate
    assert "baseline_pid_median_post_disturbance_mae" in r.aggregate
    assert r.comparison["audit"][0]["hidden_params"]["disturbances"][0]["family"] == "pump_derate"


def test_json_roundtrip(pid_heldout, pid_dist):
    for r in (pid_heldout, pid_dist):
        again = EvaluationReport.model_validate_json(r.model_dump_json())
        assert again == r
        json.dumps(r.model_dump())


def test_report_summary(pid_heldout):
    md = report_summary(pid_heldout)
    lines = md.splitlines()
    header = [i for i, ln in enumerate(lines) if ln.startswith("| index")]
    assert len(header) == 1
    rows = [ln for ln in lines[header[0] + 2:] if ln.startswith("|")]
    assert len(rows) == len(pid_heldout.episodes)


def test_agent_safe_is_blind(pid_heldout, pid_dist, const_heldout):
    for r in (pid_heldout, pid_dist, const_heldout):
        safe = r.agent_safe()
        assert not any(k.startswith("baseline") for k in safe["aggregate"])
        text = json.dumps(safe, sort_keys=True)
        assert find_leaks(text) == [], find_leaks(text)[:5]
        low = text.lower()
        for word in ("seed", "audit", "hidden"):
            assert word not in low
