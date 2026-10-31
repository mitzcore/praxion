from __future__ import annotations

import math

import pytest

from backend.safety.supervisor import SafetyLimits, Supervisor
from backend.schemas import Observation

OBS = Observation(t=10.0, y=0.5)


def test_ok_passthrough():
    s = Supervisor(SafetyLimits())
    d = s.filter(0.42, OBS, now_t=10.0)
    assert (d.u_applied, d.override, d.reason) == (0.42, False, "ok")
    assert s.override_count == 0


@pytest.mark.parametrize("bad", [math.nan, math.inf, -math.inf, "abc", None])
def test_non_finite_forces_fallback(bad):
    s = Supervisor()
    d = s.filter(bad, OBS, now_t=10.0)
    assert d.u_applied == 0.0 and d.override and d.reason == "non_finite_request"
    assert s.override_count == 1


@pytest.mark.parametrize("u,expected", [(-0.5, 0.0), (1.7, 1.0)])
def test_clamping(u, expected):
    s = Supervisor()
    d = s.filter(u, OBS, now_t=10.0)
    assert d.u_applied == expected and d.override and d.reason == "clamped"
    assert s.override_count == 1


def test_hard_cutoff_forces_zero_and_counts_violation():
    s = Supervisor()
    d = s.filter(0.9, Observation(t=1.0, y=0.91), now_t=1.0)
    assert d.u_applied == 0.0 and d.override and d.reason.startswith("hard_cutoff")
    assert s.violation_count == 1 and s.override_count == 1
    s.filter(0.0, Observation(t=1.1, y=0.90), now_t=1.1)
    assert s.violation_count == 2


def test_stale_sensor_forces_zero():
    s = Supervisor()
    d = s.filter(0.5, Observation(t=0.0, y=0.5), now_t=3.5)
    assert d.u_applied == 0.0 and d.override and d.reason.startswith("sensor_stale")
    # within timeout is fine
    assert not s.filter(0.5, Observation(t=0.0, y=0.5), now_t=3.0).override


def test_missing_sensor_and_estop():
    s = Supervisor()
    d = s.filter(0.5, None, now_t=0.0)
    assert d.u_applied == 0.0 and d.reason == "sensor_missing"
    d = s.filter(0.5, OBS, now_t=10.0, estop=True)
    assert d.u_applied == 0.0 and d.override and d.reason == "estop"
    assert s.override_count == 2


def test_override_counter_accumulates_and_resets():
    s = Supervisor()
    for u in (math.nan, 2.0, -1.0, 0.3):
        s.filter(u, OBS, now_t=10.0)
    assert s.override_count == 3
    s.reset_counters()
    assert s.override_count == 0 and s.violation_count == 0


@pytest.mark.parametrize(
    "u,dur",
    [(math.nan, 5.0), (math.inf, 5.0), (0.3, math.nan), (-0.1, 5.0), (1.1, 5.0), (0.3, 0.0), (0.3, -1.0),
     (0.3, 20.01)],
)
def test_validate_proposal_rejections(u, dur):
    v = Supervisor().validate_proposal(u, dur, Observation(t=0.0, y=0.2))
    assert not v.ok and v.u is None and v.duration_s is None


def test_validate_proposal_max_duration_ok_and_unchanged():
    v = Supervisor().validate_proposal(0.1, 20.0, Observation(t=0.0, y=0.2))
    assert v.ok and v.u == 0.1 and v.duration_s == 20.0


def test_validate_proposal_needs_observation():
    assert not Supervisor().validate_proposal(0.1, 2.0, None).ok


def test_interlock_forces_fallback_and_counts_violation():
    s = Supervisor()
    d = s.filter(0.5, Observation(t=1.0, y=0.70, interlock_high=True), now_t=1.0)
    assert d.u_applied == 0.0 and d.override and d.reason == "interlock_high"
    assert s.violation_count == 1 and s.override_count == 1


def test_interlock_takes_precedence_over_bad_request():
    d = Supervisor().filter(float("nan"), Observation(t=1.0, y=0.95, interlock_high=True), now_t=1.0)
    assert d.reason == "interlock_high"


def test_hard_cutoff_still_second_layer_without_interlock():
    d = Supervisor().filter(0.5, Observation(t=1.0, y=0.92, interlock_high=False), now_t=1.0)
    assert d.reason.startswith("hard_cutoff")


def test_zero_input_is_approved_even_when_level_is_high():
    """Draining (u=0) can never raise the level; refusing it above the soft limit blocked the safest action
    (observed in live run spark5: both after-change drain proposals rejected at y >= 0.85)."""
    from backend.schemas import Observation
    sup = Supervisor(SafetyLimits(max_single_experiment_s=40.0))
    v = sup.validate_proposal(0.0, 40.0, Observation(t=100.0, y=0.93))
    assert v.ok, v.reason
    v2 = sup.validate_proposal(0.05, 40.0, Observation(t=100.0, y=0.93))
    assert not v2.ok  # any positive input from above the soft limit is still refused
