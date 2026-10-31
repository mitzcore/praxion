from __future__ import annotations

import math

import pytest

from backend.plant.tank_sim import TankSimulator
from backend.safety.envelope import MAX_RATE_AT_FULL_DUTY, worst_case_level
from backend.safety.supervisor import Supervisor
from backend.schemas import Observation


def test_bound_formula():
    assert worst_case_level(0.3, 1.0, 5.0, 0.1) == pytest.approx(0.3 + MAX_RATE_AT_FULL_DUTY * 5.0)
    assert worst_case_level(0.3, 0.5, 2.0, 0.1) == pytest.approx(0.3 + 0.5 * MAX_RATE_AT_FULL_DUTY * 2.0)
    assert worst_case_level(0.3, 0.0, 20.0, 0.1) == pytest.approx(0.3)
    assert worst_case_level(0.3, 1.0, 0.05, 0.1) == pytest.approx(0.3 + MAX_RATE_AT_FULL_DUTY * 0.1)


def test_non_finite_gives_inf():
    assert worst_case_level(math.nan, 0.5, 1.0, 0.1) == math.inf
    assert worst_case_level(0.3, math.inf, 1.0, 0.1) == math.inf


def test_rejects_proposal_that_could_cross_soft_limit():
    sup = Supervisor()
    v = sup.validate_proposal(1.0, 10.0, Observation(t=0.0, y=0.5))
    assert not v.ok
    assert "worst-case bound" in v.reason and ">= soft limit 0.85" in v.reason


def test_accepts_clearly_safe_proposal():
    sup = Supervisor()
    v = sup.validate_proposal(0.3, 5.0, Observation(t=0.0, y=0.3))
    assert v.ok and v.u == 0.3 and v.duration_s == 5.0


@pytest.mark.parametrize("seed", list(range(1, 21)))
def test_bound_actually_upper_bounds_simulator(seed):
    """Envelope from the TRUE level over-predicts the true level for full-duty pulses."""
    p = TankSimulator()
    p.reset(seed)
    h0 = p.true_state()["h_true"]
    bound = worst_case_level(h0, 1.0, 8.0, p.dt)
    for _ in range(80):
        p.step(1.0)
    assert p.true_state()["h_true"] <= bound
