from __future__ import annotations

import math

import pytest

from backend.controller.runtime import run_constant_input, run_episode
from backend.evaluation.baselines import ConstantController, PIDController
from backend.evaluation.metrics import compute_metrics
from backend.plant.tank_sim import TankSimulator
from backend.safety.supervisor import Supervisor
from backend.schemas import DisturbanceSpec


class Exploding:
    name = "exploding"
    isolation = "trusted"

    def __init__(self, every=3):
        self.every, self.k, self.closed = every, 0, False

    def reset(self):
        self.k = 0

    def step(self, obs):
        self.k += 1
        if self.k % self.every == 0:
            raise ZeroDivisionError("boom")
        if self.k % self.every == 1:
            return "not-a-number"
        return 0.4

    def close(self):
        self.closed = True


class Recorder(ConstantController):
    def __init__(self):
        super().__init__(0.5, name="rec")
        self.obs = []

    def step(self, obs):
        self.obs.append(obs)
        return 0.5


def test_episode_shape_and_obs_contract():
    rec = Recorder()
    tr = run_episode(TankSimulator(), rec, Supervisor(), 10.0, 0.6, seed=1)
    assert len(tr.steps) == 100
    assert tr.dt == 0.1 and tr.target == 0.6 and tr.disturbance_at is None
    assert all(set(o) == {"y", "target", "dt", "elapsed_s"} for o in rec.obs)
    assert rec.obs[0]["elapsed_s"] == 0.0 and rec.obs[-1]["elapsed_s"] == pytest.approx(9.9)
    assert [s.t for s in tr.steps][:3] == [0.0, 0.1, 0.2]


def test_runtime_catches_controller_exceptions():
    c = Exploding()
    tr = run_episode(TankSimulator(), c, Supervisor(), 3.0, 0.6, seed=2, close_after=True)
    assert len(tr.steps) == 30
    exc = [s for s in tr.steps if s.reason.startswith("controller_exception")]
    assert len(exc) == 20  # both the raise and the non-numeric return
    assert {s.reason for s in exc} == {"controller_exception:ZeroDivisionError", "controller_exception:ValueError"}
    assert all(math.isnan(s.u_requested) and s.u_applied == 0.0 and s.override for s in exc)
    assert compute_metrics(tr, 0.0).invalid_outputs == 20
    assert c.closed


def test_controller_not_closed_by_default():
    c = Exploding()
    run_episode(TankSimulator(), c, Supervisor(), 1.0, 0.6, seed=2)
    assert not c.closed


def test_supervisor_cutoff_in_closed_loop():
    """A controller demanding full pump forever is cut off by the supervisor."""
    sup = Supervisor()
    tr = run_episode(TankSimulator(), ConstantController(1.0), sup, 120.0, 0.6, seed=3)
    assert sup.violation_count > 0
    assert any(s.reason.startswith("hard_cutoff") and s.u_applied == 0.0 for s in tr.steps)
    assert max(s.h_true for s in tr.steps) < 0.95


def test_disturbance_recorded_and_applied():
    d = DisturbanceSpec(family="pump_derate", at_t=30.0)
    tr = run_episode(TankSimulator(), PIDController(), Supervisor(), 60.0, 0.6, seed=2000, disturbance=d)
    assert tr.disturbance_at == 30.0
    assert tr.meta["disturbance"]["family"] == "pump_derate"


def test_run_constant_input_continues_state():
    p = TankSimulator()
    p.reset(5)
    sup = Supervisor()
    a = run_constant_input(p, sup, 0.8, 5.0, 0.6)
    b = run_constant_input(p, sup, 0.0, 5.0, 0.6)
    assert len(a.steps) == len(b.steps) == 50
    assert b.steps[0].t == pytest.approx(5.0)
    assert all(s.u_applied == 0.8 for s in a.steps)
    assert b.steps[-1].h_true < b.steps[0].h_true


def test_run_constant_input_invalid_u_is_overridden():
    p = TankSimulator()
    p.reset(5)
    tr = run_constant_input(p, Supervisor(), math.nan, 1.0, 0.6)
    assert all(s.u_applied == 0.0 and s.override for s in tr.steps)
