from __future__ import annotations

import numpy as np

from backend.controller.runtime import run_episode
from backend.evaluation.baselines import ConstantController, PIDController
from backend.plant.tank_sim import TankSimulator
from backend.safety.supervisor import Supervisor
from backend.schemas import DisturbanceSpec


def _inputs(n: int) -> list[float]:
    rng = np.random.default_rng(123)
    return [float(x) for x in rng.uniform(0, 1, n)]


def _roll(seed: int, us: list[float]) -> list[tuple[float, float, float]]:
    p = TankSimulator()
    p.reset(seed)
    out = []
    for u in us:
        o = p.step(u)
        out.append((o.t, o.y, p.true_state()["h_true"]))
    return out


def test_same_seed_same_inputs_identical():
    us = _inputs(600)
    assert _roll(7, us) == _roll(7, us)


def test_reset_is_repeatable_on_same_instance():
    us = _inputs(200)
    p = TankSimulator()
    p.reset(3)
    a = [p.step(u).y for u in us]
    p.reset(3)
    b = [p.step(u).y for u in us]
    assert a == b


def test_different_seeds_different_params_and_traces():
    a, b = TankSimulator(), TankSimulator()
    a.reset(1)
    b.reset(2)
    pa, pb = a.hidden_params(), b.hidden_params()
    assert any(pa[k] != pb[k] for k in ("tank_area", "pump_gain", "drain_coeff", "tau"))
    us = _inputs(100)
    assert _roll(1, us) != _roll(2, us)


def test_observe_does_not_advance_or_consume_noise():
    us = _inputs(50)
    p = TankSimulator()
    p.reset(5)
    vals = []
    for u in us:
        o1, o2 = p.observe(), p.observe()
        assert o1 == o2
        vals.append(p.step(u).y)
    p2 = TankSimulator()
    p2.reset(5)
    assert vals == [p2.step(u).y for u in us]


def test_noise_stream_independent_of_disturbance_scheduling():
    """Scheduling a disturbance must not shift the noise draws before it takes effect."""
    us = _inputs(300)
    p1, p2 = TankSimulator(), TankSimulator()
    p1.reset(11)
    p2.reset(11)
    p2.schedule_disturbance(DisturbanceSpec(family="pump_derate", at_t=20.0))
    y1 = [p1.step(u).y for u in us]
    y2 = [p2.step(u).y for u in us]
    assert y1[:200] == y2[:200]
    assert y1[250:] != y2[250:]


def test_runtime_episode_deterministic():
    for ctrl in (PIDController, lambda: ConstantController(0.6)):
        t1 = run_episode(TankSimulator(), ctrl(), Supervisor(), 60.0, 0.6, seed=4)
        t2 = run_episode(TankSimulator(), ctrl(), Supervisor(), 60.0, 0.6, seed=4)
        assert t1.steps == t2.steps


def _roll_scen(seed: int, scenario: int | None, us: list[float]) -> list[tuple[float, float, float]]:
    p = TankSimulator()
    p.reset(seed, scenario)
    out = []
    for u in us:
        o = p.step(u)
        out.append((o.t, o.y, p.true_state()["h_true"]))
    return out


def test_reset_seed_equals_reset_seed_seed():
    us = _inputs(300)
    assert _roll_scen(9, None, us) == _roll_scen(9, 9, us)
    a, b = TankSimulator(), TankSimulator()
    a.reset(9)
    b.reset(9, 9)
    assert a.hidden_params() == b.hidden_params()


def test_same_seed_and_scenario_identical():
    us = _inputs(300)
    assert _roll_scen(3, 2001, us) == _roll_scen(3, 2001, us)


PHYSICAL = ("tank_area", "pump_gain", "deadband", "tau", "drain_coeff", "leak_base", "noise_std", "delay_nominal")


def test_scenario_changes_episode_not_machine():
    a, b = TankSimulator(), TankSimulator()
    a.reset(4, 2000)
    b.reset(4, 2001)
    pa, pb = a.hidden_params(), b.hidden_params()
    assert all(pa[k] == pb[k] for k in PHYSICAL)
    assert pa["h0"] != pb["h0"]
    assert pa["disturbance_defaults"] != pb["disturbance_defaults"]
    assert (pa["seed"], pa["scenario"]) == (4, 2000) and (pb["seed"], pb["scenario"]) == (4, 2001)
    us = _inputs(100)
    assert _roll_scen(4, 2000, us) != _roll_scen(4, 2001, us)


def test_seed_changes_machine_not_episode():
    a, b = TankSimulator(), TankSimulator()
    a.reset(1, 2003)
    b.reset(2, 2003)
    pa, pb = a.hidden_params(), b.hidden_params()
    assert all(pa[k] != pb[k] for k in PHYSICAL)
    assert pa["h0"] == pb["h0"]
    assert pa["disturbance_defaults"] == pb["disturbance_defaults"]


def test_runtime_passes_scenario_through():
    t1 = run_episode(TankSimulator(), PIDController(), Supervisor(), 20.0, 0.6, seed=2, scenario=1005)
    p = TankSimulator()
    p.reset(2, 1005)
    assert t1.steps[0].h_true == p.true_state()["h_true"]
    assert t1.meta["seed"] == 2 and t1.meta["scenario"] == 1005
    t2 = run_episode(TankSimulator(), PIDController(), Supervisor(), 20.0, 0.6, seed=2)
    assert t2.meta["scenario"] == 2
    assert t1.steps != t2.steps
