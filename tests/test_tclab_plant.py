"""TCLabSim (deterministic TCLabModel wrapper) and TCLabHardware (fake board only, no serial)."""
from __future__ import annotations

import math

import numpy as np
import pytest

from backend.agent.view import find_leaks
from backend.plant import tclab_plant as tp
from backend.plant.tclab_plant import INTERLOCK_C, TCLabHardware, TCLabSim, normalize
from backend.schemas import DisturbanceSpec, Trace, TraceStep


def _run(plant, u, n):
    ys, hs = [], []
    for _ in range(n):
        ys.append(plant.observe().y)
        hs.append(plant.true_state()["h_true"])
        plant.step(u)
    return np.array(ys), np.array(hs)


def _temp(plant) -> float:
    return plant.true_state()["h_true"] * 60.0 + 15.0


# ------------------------------------------------------------------ TCLabSim
def test_import_does_not_need_hardware():
    hw = TCLabHardware(port="/dev/does-not-exist")  # constructing must not open serial
    assert hw._lab is None
    hw.close()


def test_deterministic_under_seed_and_scenario():
    a, b = TCLabSim(), TCLabSim()
    a.reset(3, 7)
    b.reset(3, 7)
    ya, ha = _run(a, 0.6, 120)
    yb, hb = _run(b, 0.6, 120)
    assert np.array_equal(ya, yb) and np.array_equal(ha, hb)
    c = TCLabSim()
    c.reset(3, 8)  # different scenario: different room and noise
    yc, _ = _run(c, 0.6, 120)
    assert not np.array_equal(ya, yc)
    assert a.hidden_params()["gain_scale"] == c.hidden_params()["gain_scale"]  # same machine


def test_scenario_varies_ambient_in_range():
    tas = []
    for sc in range(20):
        s = TCLabSim()
        s.reset(0, sc)
        tas.append(s.hidden_params()["Ta_c"])
        assert abs(_temp(s) - tas[-1]) < 1e-9  # starts in equilibrium with the room
    assert min(tas) >= 18.0 and max(tas) <= 26.0 and max(tas) - min(tas) > 3.0


def test_step_advances_exactly_one_second():
    s = TCLabSim()
    obs = s.reset(0)
    assert s.dt == 1.0 and obs.t == 0.0
    for k in range(1, 6):
        assert s.step(0.2).t == float(k)
    assert s.true_state()["t"] == 5.0


def test_heating_and_cooling():
    s = TCLabSim()
    s.reset(1, 1)
    Ta = s.hidden_params()["Ta_c"]
    _run(s, 1.0, 200)
    hot = _temp(s)
    assert hot > Ta + 25.0
    _run(s, 0.0, 900)
    cold = _temp(s)
    assert Ta < cold < hot - 20.0  # decays toward ambient
    _, h = _run(s, 0.0, 50)
    assert np.all(np.diff(h) <= 1e-12)


def test_observation_normalization_and_noise():
    s = TCLabSim()
    s.reset(2, 2)
    _run(s, 0.7, 150)
    y = s.observe().y
    assert 0.0 <= y <= 1.0
    assert abs(y - s.true_state()["h_true"]) < 0.5 / 60.0  # noise 0.043 °C + 0.32 °C quantization


def test_interlock_trips_above_69c():
    s = TCLabSim()
    s.reset(0, 0)
    tripped_at = None
    for _ in range(1500):
        obs = s.step(1.0)
        if obs.interlock_high:
            tripped_at = _temp(s)
            break
    assert tripped_at is not None and tripped_at >= INTERLOCK_C
    assert tripped_at < INTERLOCK_C + 0.5
    assert s.observe().y >= 0.89


def test_input_validation():
    s = TCLabSim()
    s.reset(0)
    for bad in (math.nan, -0.1, 1.1, "x"):
        with pytest.raises(ValueError):
            s.step(bad)


def test_full_power_heating_rate_within_envelope():
    """The supervisor envelope (profiles.TCLAB_*.worst_case_rate_per_unit_u) must bound the
    fastest heating rate at u = 1 for every machine seed."""
    from backend.profiles import TCLAB_SIM

    worst = 0.0
    for seed in range(30):
        s = TCLabSim()
        s.reset(seed, 0)
        _, h = _run(s, 1.0, 120)
        worst = max(worst, float(np.max(np.diff(h))))
    assert worst <= TCLAB_SIM.worst_case_rate_per_unit_u, worst


def _response(family, magnitude=None, u=0.5, at=0.0, n=400, seed=4, scenario=4):
    s = TCLabSim()
    s.reset(seed, scenario)
    if family is not None:
        s.schedule_disturbance(DisturbanceSpec(family=family, at_t=at, magnitude=magnitude))
    _, h = _run(s, u, n)
    return h, s


def test_pump_derate_lowers_temperature():
    base, _ = _response(None)
    dist, s = _response("pump_derate")
    m = s.hidden_params()["disturbances"][0]["applied"]["magnitude"]
    assert 0.25 <= m <= 0.40
    assert dist[-1] < base[-1] - 0.03


@pytest.mark.parametrize("family", ["extra_leak", "drain_shift"])
def test_extra_loss_lowers_temperature(family):
    base, _ = _response(None)
    dist, _ = _response(family)
    assert dist[-1] < base[-1] - 0.02


def test_extra_leak_cools_faster_from_hot():
    s1, s2 = TCLabSim(), TCLabSim()
    for s in (s1, s2):
        s.reset(5, 5)
        _run(s, 0.8, 300)
    s2.schedule_disturbance(DisturbanceSpec(family="extra_leak", at_t=300.0))
    _, h1 = _run(s1, 0.0, 200)
    _, h2 = _run(s2, 0.0, 200)
    assert h2[-1] < h1[-1]


def test_drain_shift_default_smaller_than_extra_leak():
    _, s = _response(None, n=1)
    d = s.hidden_params()["disturbance_defaults"]
    assert d["drain_shift"] < d["extra_leak"]


def test_actuator_lag_delays_response():
    base, _ = _response(None, u=1.0, n=240)
    lag, s = _response("actuator_lag", u=1.0, n=240)
    delay = s.hidden_params()["disturbances"][0]["applied"]["magnitude"]
    assert 90.0 <= delay <= 150.0
    k = int(delay) - 1
    assert abs(lag[k] - lag[0]) < 1e-9  # heater has not seen any command yet
    assert lag[160] < base[160] - 0.01
    # explicit magnitude = seconds
    lag10, _ = _response("actuator_lag", magnitude=10.0, u=1.0, n=60)
    assert lag10[30] > lag[30]


def test_disturbance_not_before_at_t():
    base, _ = _response(None, n=200)
    dist, _ = _response("pump_derate", at=150.0, n=200)
    assert np.array_equal(base[:151], dist[:151])
    assert dist[-1] < base[-1]


def test_emergency_stop_flushes_delay():
    s = TCLabSim()
    s.reset(0, 0)
    s.schedule_disturbance(DisturbanceSpec(family="actuator_lag", at_t=0.0, magnitude=30.0))
    _run(s, 1.0, 20)  # 20 s of full-power commands queued, none applied yet
    s.emergency_stop()
    _, h = _run(s, 0.0, 60)
    assert np.all(np.diff(h) <= 1e-12)


def test_public_description_and_agent_safe_projection_has_no_hidden_fields():
    s = TCLabSim()
    s.reset(1001, 2003)
    desc = s.public_description()
    assert "0 = 15 °C, 1 = 75 °C" in desc
    assert not any(ch.isdigit() for ch in desc.replace("[0,1]", "").replace("0 = 15 °C, 1 = 75 °C", ""))
    s.schedule_disturbance(DisturbanceSpec(family="extra_leak", at_t=30.0))
    steps = []
    for _ in range(90):
        o = s.observe()
        h = s.true_state()["h_true"]
        s.step(0.4)
        steps.append(TraceStep(t=o.t, y=o.y, h_true=h, u_requested=0.4, u_applied=0.4, override=False, reason="ok"))
    tr = Trace(steps=steps, dt=1.0, target=0.4167, disturbance_at=30.0, meta={"hidden": s.hidden_params()})
    view = {"plant": {"description": desc}, "trace": tr.agent_safe(), "summary": tr.measured_summary()}
    assert find_leaks(view) == []
    # sanity: the leak checker would catch the hidden data if it were included
    assert find_leaks({"hidden": s.hidden_params()}) != []


# ------------------------------------------------------------------ TCLabHardware (fake board)
class FakeClock:
    def __init__(self):
        self.now = 100.0
        self.sleeps: list[float] = []

    def __call__(self) -> float:
        return self.now

    def sleep(self, d: float) -> None:
        self.sleeps.append(d)
        self.now += d


class FakeLab:
    def __init__(self, clock: FakeClock, temps=None, cool_rate=0.0):
        self.clock = clock
        self.T = 30.0
        self.cool_rate = cool_rate
        self.q1: list[float] = []
        self.q2: list[float] = []
        self.closed = False
        self._temps = list(temps) if temps else None

    @property
    def T1(self) -> float:
        if self._temps:
            return self._temps.pop(0) if len(self._temps) > 1 else self._temps[0]
        return self.T

    def Q1(self, v=None):
        if v is not None:
            self.q1.append(float(v))
        return self.q1[-1] if self.q1 else 0.0

    def Q2(self, v=None):
        if v is not None:
            self.q2.append(float(v))
        return self.q2[-1] if self.q2 else 0.0

    def close(self):
        self.closed = True


def _hw(lab_temps=None):
    clk = FakeClock()
    lab = FakeLab(clk, temps=lab_temps)
    hw = TCLabHardware(lab_factory=lambda: lab, clock=clk, sleep=clk.sleep)
    return hw, lab, clk


def test_hw_normalization_and_interlock():
    assert normalize(15.0) == 0.0 and normalize(75.0) == 1.0 and normalize(10.0) == 0.0
    assert normalize(95.0) == 1.0 and abs(normalize(45.0) - 0.5) < 1e-12
    hw, lab, _ = _hw()
    hw.reset(0)
    lab.T = 68.9
    assert hw.observe().interlock_high is False
    lab.T = 69.0
    o = hw.observe()
    assert o.interlock_high is True and abs(o.y - 0.9) < 1e-12
    assert hw.true_state()["h_true"] == pytest.approx(0.9)


def test_hw_reset_turns_heaters_off_and_waits_for_cooldown():
    hw, lab, clk = _hw(lab_temps=[40.0, 39.0, 36.0, 34.9])
    obs = hw.reset(0)
    assert lab.q1[-1] == 0.0 and lab.q2[-1] == 0.0
    assert obs.t == 0.0 and clk.sleeps == [1.0, 1.0, 1.0]


def test_hw_reset_times_out(caplog):
    hw, _lab, clk = _hw(lab_temps=[50.0])
    with caplog.at_level("WARNING"):
        hw.reset(0)
    assert sum(clk.sleeps) == pytest.approx(120.0)
    assert "timeout" in caplog.text


def test_hw_step_sets_q1_and_ticks_on_fixed_schedule():
    hw, lab, clk = _hw()
    hw.reset(0)
    t_start = clk.now
    for k in range(5):
        clk.now += 0.137  # controller + serial latency each tick
        o = hw.step(0.42)
        assert o.t == float(k + 1)
        assert lab.q1[-1] == pytest.approx(42.0)
    # tick k ends at t_start + 0.137 + (k+1)*1.0: latency does not accumulate
    assert clk.now == pytest.approx(t_start + 0.137 + 5.0)
    assert hw.overruns == 0


def test_hw_overrun_reanchors():
    hw, _lab, clk = _hw()
    hw.reset(0)
    hw.step(0.1)
    clk.now += 3.5  # a stall
    hw.step(0.1)
    assert hw.overruns == 1
    t = clk.now
    hw.step(0.1)
    assert clk.now == pytest.approx(t + 1.0)


def test_hw_step_validates_and_disturbance_not_supported():
    hw, _lab, _ = _hw()
    hw.reset(0)
    with pytest.raises(ValueError):
        hw.step(1.5)
    with pytest.raises(NotImplementedError, match="operator"):
        hw.schedule_disturbance(DisturbanceSpec(family="extra_leak", at_t=10.0))


def test_hw_emergency_stop_and_close():
    hw, lab, _ = _hw()
    hw.reset(0)
    hw.step(0.9)
    hw.emergency_stop()
    assert lab.q1[-1] == 0.0 and lab.q2[-1] == 0.0
    hw.step(0.9)
    hw.close()
    assert lab.q1[-1] == 0.0 and lab.closed and hw._lab is None
    assert hw not in tp._LIVE_BOARDS


def test_atexit_hook_turns_heaters_off():
    hw, lab, _ = _hw()
    hw.reset(0)
    hw.step(0.7)
    tp._heaters_off_at_exit()
    assert lab.q1[-1] == 0.0 and lab.q2[-1] == 0.0
