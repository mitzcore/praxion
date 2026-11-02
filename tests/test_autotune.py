"""Classical relay auto-tuned baselines (evaluation/autotune.py). Exploration seeds only; never hidden seeds."""
from __future__ import annotations

import math

import pytest

from backend.controller.runtime import run_episode
from backend.evaluation import autotune as at
from backend.evaluation.baselines import PIDController
from backend.evaluation.config import DISTURBANCE_AT_S, DISTURBANCE_EPISODE_S, EPISODE_S, SETTLE_S, TARGET
from backend.evaluation.metrics import compute_metrics
from backend.plant.tank_sim import TankSimulator
from backend.profiles import TANK
from backend.safety.supervisor import Supervisor
from backend.schemas import DisturbanceSpec


def _nominal_metrics(report, seed):
    tr = run_episode(TankSimulator(), at.controller_from(report), Supervisor(), EPISODE_S, TARGET, seed)
    return compute_metrics(tr, SETTLE_S)


def _post_metrics(report, seed, family):
    d = DisturbanceSpec(family=family, at_t=DISTURBANCE_AT_S)
    tr = run_episode(TankSimulator(), at.controller_from(report), Supervisor(), DISTURBANCE_EPISODE_S, TARGET, seed,
                     disturbance=d)
    return compute_metrics(tr, DISTURBANCE_AT_S + SETTLE_S)


def test_tuning_rules_shapes():
    g = at.tuning_rule(10.0, 8.0, "tl_pi")
    assert g["kp"] == pytest.approx(10.0 / 3.2) and g["ki"] == pytest.approx(g["kp"] / (2.2 * 8.0)) and g["kd"] == 0.0
    assert at.RULE in at.TUNING_RULES


@pytest.mark.parametrize("seed", list(range(1, 21)))
def test_nominal_autotune_is_deterministic_safe_and_within_budget(seed):
    a, b = at.autotune_nominal(seed), at.autotune_nominal(seed)
    assert a.model_dump() == b.model_dump()
    assert a.fallback_reason is None and a.source_estimate is not None
    assert a.plant_s_total <= TANK.max_experiments * TANK.max_single_experiment_s == a.budget_s
    assert a.hard_violations_total == 0 and all(s.overrides == 0 for s in a.stages)
    assert all(s.max_y < TANK.soft_high_limit for s in a.stages)
    g = a.gains
    assert all(math.isfinite(v) for v in g.values()) and g["kp"] > 0 and g["ki"] > 0 and 0.0 < g["u_bias"] < 1.0
    s1 = a.stages[0]
    assert s1.ok and 2.0 < s1.Pu < 60.0 and s1.Ku > 0


@pytest.mark.parametrize("seed", list(range(1, 11)))
def test_nominal_relay_pi_holds_band_on_exploration_seeds(seed):
    m = _nominal_metrics(at.autotune_nominal(seed), seed)
    assert m.in_band_fraction >= 0.70 and m.hard_violations == 0 and m.override_count == 0 and m.invalid_outputs == 0


@pytest.mark.parametrize("seed", [1, 2, 3])
def test_after_change_retunes_under_actuator_lag(seed):
    nominal = at.autotune_nominal(seed)
    rep = at.autotune_after_change(seed, "actuator_lag", nominal)
    assert rep.detector_fired_at_s is not None and rep.detector_fired_at_s > TANK.monitor_pre_s
    assert rep.retuned and rep.fallback_reason is None
    seg = rep.stages[-1]
    assert seg.ok and seg.cycles >= at.N_CYCLES and seg.Pu > 30.0  # the 18-22 s delay shows up as a long period
    assert rep.gains["kp"] < nominal.gains["kp"] and rep.gains["ki"] < nominal.gains["ki"]
    assert rep.plant_s_total <= at.RETUNE_CAP_S
    # the re-tuned loop recovers on the (exploration) plant-seed scenario; the nominal one does not
    assert _post_metrics(rep, seed, "actuator_lag").in_band_fraction >= 0.70
    assert _post_metrics(nominal, seed, "actuator_lag").in_band_fraction < 0.70
    assert "monitor fired" in at.summary_note(rep)


def test_after_change_keeps_nominal_gains_when_monitor_is_silent():
    nominal = at.autotune_nominal(1)
    rep = at.autotune_after_change(1, "pump_derate", nominal)
    assert rep.detector_fired_at_s is None and not rep.retuned and rep.gains == nominal.gains
    assert "did not fire" in at.summary_note(rep) and rep.plant_s_total == 0.0


def test_controller_names_and_bias():
    nominal = at.autotune_nominal(2)
    c = at.controller_from(nominal)
    assert isinstance(c, PIDController) and c.name == "baseline_relay_pi" and c.u_bias == nominal.gains["u_bias"]
    d = at.report_dict(nominal)
    assert d["note"].startswith("relay auto-tune on the nominal machine") and "hard_violations_total" in d
