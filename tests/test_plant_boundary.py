from __future__ import annotations

import math

import pytest

from backend.evaluation.config import TARGET
from backend.plant.tank_sim import (
    DEFAULT_DRAIN_SHIFT,
    DEFAULT_EXTRA_LEAK_DROP,
    DEFAULT_LAG_DELAY_S,
    DEFAULT_LAG_TAU_FACTOR,
    DEFAULT_PUMP_DERATE,
    DELAY_NOMINAL_RANGE,
    EXTRA_LEAK_REF_LEVEL,
    PARAM_RANGES,
    SCENARIO_RANGES,
    TankSimulator,
)
from backend.safety.envelope import MAX_RATE_AT_FULL_DUTY
from backend.schemas import DisturbanceSpec

SEEDS = list(range(1, 21)) + list(range(1000, 1010)) + list(range(2000, 2005))


def _plant(seed: int) -> TankSimulator:
    p = TankSimulator()
    p.reset(seed)
    return p


def _hold(p: TankSimulator, u: float, seconds: float) -> float:
    for _ in range(round(seconds / p.dt)):
        p.step(u)
    return p.true_state()["h_true"]


@pytest.mark.parametrize("seed", SEEDS)
def test_hidden_params_within_ranges(seed):
    hp = _plant(seed).hidden_params()
    for k, (lo, hi) in {**PARAM_RANGES, **SCENARIO_RANGES}.items():
        assert lo <= hp[k] <= hi, k
    d = hp["disturbance_defaults"]
    assert DEFAULT_PUMP_DERATE[0] <= d["pump_derate"] <= DEFAULT_PUMP_DERATE[1]
    assert DEFAULT_DRAIN_SHIFT[0] <= d["drain_shift"] <= DEFAULT_DRAIN_SHIFT[1]
    assert DEFAULT_EXTRA_LEAK_DROP[0] <= d["extra_leak_drop"] <= DEFAULT_EXTRA_LEAK_DROP[1]
    assert DEFAULT_LAG_TAU_FACTOR[0] <= d["lag_tau_factor"] <= DEFAULT_LAG_TAU_FACTOR[1]
    assert DEFAULT_LAG_DELAY_S[0] <= d["lag_delay_s"] <= DEFAULT_LAG_DELAY_S[1]
    assert DELAY_NOMINAL_RANGE[0] <= hp["delay_nominal"] <= DELAY_NOMINAL_RANGE[1]


def test_range_corners_satisfy_properties_analytically():
    """Worst corners of the sampling ranges (not just sampled seeds) keep every property."""
    a_lo, a_hi = PARAM_RANGES["tank_area"]
    g_lo, _ = PARAM_RANGES["pump_gain"]
    c_lo, c_hi = PARAM_RANGES["drain_coeff"]
    leak_hi = PARAM_RANGES["leak_base"][1]
    ss = lambda q, c: ((q - leak_hi) / c) ** 2  # steady state at u=1
    assert ss(g_lo, c_hi) > 0.9
    assert ss(g_lo * (1 - DEFAULT_PUMP_DERATE[1]), c_hi) >= 0.65
    assert ss(g_lo, c_hi * (1 + DEFAULT_DRAIN_SHIFT[1])) >= 0.65
    worst_leak = c_hi * (math.sqrt(EXTRA_LEAK_REF_LEVEL) - math.sqrt(EXTRA_LEAK_REF_LEVEL - DEFAULT_EXTRA_LEAK_DROP[1]))
    assert ss(g_lo - worst_leak, c_hi) >= 0.65
    k = 2 * math.sqrt(TARGET)
    assert 15.0 <= a_lo * k / c_hi and a_hi * k / c_lo <= 45.0


def test_envelope_is_conservative_over_whole_range():
    assert PARAM_RANGES["pump_gain"][1] / PARAM_RANGES["tank_area"][0] <= MAX_RATE_AT_FULL_DUTY + 1e-12


@pytest.mark.parametrize("seed", list(range(1, 11)))
def test_steady_state_full_duty_exceeds_0p9(seed):
    p = _plant(seed)
    assert _hold(p, 1.0, 200.0) > 0.9


@pytest.mark.parametrize("seed", list(range(1, 11)))
def test_steady_state_zero_duty_is_zero(seed):
    p = _plant(seed)
    assert _hold(p, 0.0, 400.0) == pytest.approx(0.0, abs=1e-6)


@pytest.mark.parametrize("seed", SEEDS)
def test_linearised_time_constant_near_target(seed):
    hp = _plant(seed).hidden_params()
    tau_ol = hp["tank_area"] / (hp["drain_coeff"] / (2 * math.sqrt(TARGET)))
    assert 15.0 <= tau_ol <= 45.0


@pytest.mark.parametrize("seed", [1, 5, 9])
def test_simulated_step_response_time_constant(seed):
    """Open-loop: settle at the duty holding 0.5, step to the duty holding 0.6, time to 63%."""
    p = _plant(seed)
    hp = p.hidden_params()

    def duty_for(h):
        q = hp["leak_base"] + hp["drain_coeff"] * math.sqrt(h)
        db = hp["deadband"]
        return db + (1 - db) * q / hp["pump_gain"]

    h_a = _hold(p, duty_for(0.5), 400.0)
    assert h_a == pytest.approx(0.5, abs=0.01)
    u_b = duty_for(0.6)
    t, h = 0.0, h_a
    while h < h_a + 0.632 * (0.6 - h_a) and t < 200:
        p.step(u_b)
        t += p.dt
        h = p.true_state()["h_true"]
    assert 10.0 <= t <= 50.0


@pytest.mark.parametrize("seed", list(range(2000, 2005)) + [1, 2, 3])
@pytest.mark.parametrize("family", ["pump_derate", "extra_leak", "drain_shift", "actuator_lag"])
def test_target_reachable_after_default_disturbance(seed, family):
    p = _plant(seed)
    p.schedule_disturbance(DisturbanceSpec(family=family, at_t=0.0))
    assert _hold(p, 1.0, 300.0) >= 0.65


@pytest.mark.parametrize("seed", list(range(2000, 2005)))
def test_extra_leak_default_drops_steady_state(seed):
    p = _plant(seed)
    hp = p.hidden_params()
    db = hp["deadband"]
    u = db + (1 - db) * (hp["leak_base"] + hp["drain_coeff"] * math.sqrt(TARGET)) / hp["pump_gain"]
    h_pre = _hold(p, u, 400.0)
    assert h_pre == pytest.approx(TARGET, abs=0.01)
    p.schedule_disturbance(DisturbanceSpec(family="extra_leak", at_t=p.true_state()["t"]))
    h_post = _hold(p, u, 600.0)
    assert h_pre - h_post >= 0.15


@pytest.mark.parametrize("seed", [1, 2000])
def test_pump_derate_and_drain_shift_lower_level(seed):
    base = _plant(seed)
    h0 = _hold(base, 0.7, 300.0)
    for fam in ("pump_derate", "drain_shift"):
        p = _plant(seed)
        p.schedule_disturbance(DisturbanceSpec(family=fam, at_t=0.0))
        assert _hold(p, 0.7, 300.0) < h0 - 0.05


@pytest.mark.parametrize("bad", [math.nan, math.inf, -math.inf, -0.01, 1.01, "x", None])
def test_step_rejects_invalid_input(bad):
    p = _plant(1)
    with pytest.raises(ValueError):
        p.step(bad)


def test_step_requires_reset():
    with pytest.raises(RuntimeError):
        TankSimulator().step(0.5)


def test_observation_bounds_and_time():
    p = _plant(3)
    for k in range(1, 300):
        o = p.step(1.0)
        assert 0.0 <= o.y <= 1.0
        assert o.t == pytest.approx(k * p.dt)
    assert set(p.true_state()) == {"h_true", "t"}


def test_emergency_stop_zeroes_actuator():
    p = _plant(2)
    _hold(p, 1.0, 20.0)
    h_before = p.true_state()["h_true"]
    p.emergency_stop()
    p.step(0.0)
    # with actuator at 0 the level can only fall
    assert p.true_state()["h_true"] <= h_before


def test_public_description_has_no_numbers_or_param_names():
    desc = TankSimulator().public_description()
    for name in {**PARAM_RANGES, **SCENARIO_RANGES}:
        assert name not in desc
    for word in ("area", "gain", "deadband", "tau", "coeff", "leak", "noise_std", "seed"):
        assert word not in desc.lower()
    assert not any(ch.isdigit() and ch not in "01" for ch in desc)


def _first_response_time(p: TankSimulator, n_settle: int = 100) -> float:
    """Hold u=0 (level falls), then step u=1 and return seconds until h starts rising."""
    for _ in range(n_settle):
        p.step(0.0)
    h_prev = p.true_state()["h_true"]
    t = 0.0
    while t < 60.0:
        p.step(1.0)
        t += p.dt
        h = p.true_state()["h_true"]
        if h > h_prev:
            return t
        h_prev = h
    return math.inf


@pytest.mark.parametrize("seed", [1, 2000, 2003])
def test_actuator_lag_inserts_transport_delay(seed):
    nominal = _plant(seed)
    hp = nominal.hidden_params()
    t_nom = _first_response_time(nominal)
    lagged = _plant(seed)
    lagged.schedule_disturbance(DisturbanceSpec(family="actuator_lag", at_t=0.0))
    t_lag = _first_response_time(lagged)
    assert t_nom >= hp["delay_nominal"] - 0.11
    assert t_lag >= hp["delay_nominal"] + hp["disturbance_defaults"]["lag_delay_s"] - 0.11
    assert t_lag > t_nom + 10.0
    applied = lagged.hidden_params()["disturbances"][0]["applied"]
    assert applied == {
        "tau_factor": hp["disturbance_defaults"]["lag_tau_factor"],
        "delay_s": hp["disturbance_defaults"]["lag_delay_s"],
    }


def test_actuator_lag_no_effect_before_onset():
    a, b = _plant(2001), _plant(2001)
    b.schedule_disturbance(DisturbanceSpec(family="actuator_lag", at_t=30.0))
    ya = [a.step(0.7).y for _ in range(300)]
    yb = [b.step(0.7).y for _ in range(300)]
    assert ya == yb
    assert [a.step(0.2).y for _ in range(100)] != [b.step(0.2).y for _ in range(100)]


def test_emergency_stop_flushes_delay_line():
    p = _plant(2002)
    p.schedule_disturbance(DisturbanceSpec(family="actuator_lag", at_t=0.0))
    for _ in range(100):
        p.step(1.0)  # queued full-pump commands in the delay line
    p.emergency_stop()
    h = p.true_state()["h_true"]
    for _ in range(300):
        p.step(0.0)
        assert p.true_state()["h_true"] <= h + 1e-12
        h = p.true_state()["h_true"]
