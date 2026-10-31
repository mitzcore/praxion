"""Independent high-level interlock: closes the overflow gap under actuator/transport delay."""
from __future__ import annotations

import pytest

from backend.controller.runtime import run_constant_input, run_episode
from backend.evaluation.baselines import ConstantController, PIDController
from backend.evaluation.config import (
    DISTURBANCE_AT_S,
    DISTURBANCE_EPISODE_S,
    DISTURBANCE_SEEDS,
    EPISODE_S,
    EXPLORATION_SEEDS,
    HELDOUT_SEEDS,
    TARGET,
)
from backend.evaluation.metrics import compute_metrics
from backend.plant.tank_sim import INTERLOCK_LEVEL, TankSimulator
from backend.safety.supervisor import Supervisor
from backend.schemas import DisturbanceSpec

LAG = DisturbanceSpec(family="actuator_lag", at_t=DISTURBANCE_AT_S)


def test_observe_reports_interlock_from_true_level():
    p = TankSimulator()
    p.reset(1)
    assert p.observe().interlock_high is False
    while p.true_state()["h_true"] < INTERLOCK_LEVEL:
        p.step(1.0)
    assert p.observe().interlock_high is True


@pytest.mark.parametrize("plant", EXPLORATION_SEEDS[:5])
def test_bad_controller_under_actuator_lag_is_contained(plant):
    """(a) full-pump controller + actuator_lag on the frozen disturbance scenarios."""
    for scen in DISTURBANCE_SEEDS:
        tr = run_episode(TankSimulator(), ConstantController(1.0), Supervisor(), DISTURBANCE_EPISODE_S, TARGET,
                         plant, scenario=scen, disturbance=LAG)
        assert tr.h_true().max() <= INTERLOCK_LEVEL + 0.02, (plant, scen)
        assert any(s.reason == "interlock_high" for s in tr.steps)


@pytest.mark.parametrize("plant,scen", [(2019, 2019), (2020, 2020), (8, 2010), (19, 2020)])
def test_previous_overflow_cases_now_bounded(plant, scen):
    """(b) default-PID cases that overflowed to h=1.0 before the interlock (sweep of plants 1-20 x
    scenarios 2000-2024, incl. reset(s) for s in 2005-2024). Violations still count."""
    tr = run_episode(TankSimulator(), PIDController(), Supervisor(), DISTURBANCE_EPISODE_S, TARGET,
                     plant, scenario=scen, disturbance=LAG)
    assert tr.h_true().max() <= 0.92
    if (plant, scen) != (2019, 2019):  # 2019 now stays just below the line thanks to the y-cutoff flush
        assert compute_metrics(tr, 0.0).hard_violations >= 1


@pytest.mark.parametrize("plant", EXPLORATION_SEEDS[:10])
def test_nominal_pid_never_trips_interlock(plant):
    """(c)"""
    for scen in [plant, *HELDOUT_SEEDS[:3]]:
        tr = run_episode(TankSimulator(), PIDController(), Supervisor(), EPISODE_S, TARGET, plant, scenario=scen)
        assert not any(s.reason.startswith(("interlock_high", "hard_cutoff")) for s in tr.steps)


def test_constant_input_trip_flushes_delay_line():
    p = TankSimulator()
    p.reset(3, 2001)
    p.schedule_disturbance(DisturbanceSpec(family="actuator_lag", at_t=0.0))
    tr = run_constant_input(p, Supervisor(), 1.0, 200.0, TARGET)
    assert any(s.reason == "interlock_high" for s in tr.steps)
    assert tr.h_true().max() <= INTERLOCK_LEVEL + 0.02
