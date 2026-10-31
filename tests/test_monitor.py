"""Trusted degradation monitor (backend/evaluation/monitor.py)."""
from __future__ import annotations

import inspect
import json

import numpy as np
import pytest

from backend.controller.runtime import run_episode as _run_episode
from backend.evaluation.baselines import ConstantController, PIDController
from backend.evaluation.config import DEGRADATION_FLOOR, DEGRADATION_HOLD_S, DEGRADATION_WINDOW_S
from backend.evaluation.monitor import DegradationDetector, MonitoredResult, run_monitored_rollout
from backend.plant.tank_sim import TankSimulator
from backend.safety.supervisor import Supervisor
from backend.schemas import DisturbanceSpec

pytestmark = pytest.mark.skipif(
    "scenario" not in inspect.signature(_run_episode).parameters,
    reason="runtime.run_episode does not accept `scenario` yet (plant_seed/scenario split not landed)",
)

DT = 0.1


def test_defaults_come_from_config():
    d = DegradationDetector(DT)
    th = d.thresholds()
    assert th["window_s"] == DEGRADATION_WINDOW_S and th["hold_s"] == DEGRADATION_HOLD_S
    assert th["floor"] == DEGRADATION_FLOOR and th["threshold"] is None


def test_fires_on_synthetic_step_offset():
    rng = np.random.default_rng(0)
    d = DegradationDetector(DT)
    target, step_t = 0.6, 60.0
    fired_at = None
    for k in range(int(150 / DT)):
        t = round(k * DT, 1)
        y = target + rng.normal(0, 0.005) + (0.1 if t >= step_t else 0.0)
        if d.update(t, y, target) and fired_at is None:
            fired_at = t
        if t == 45.0:
            d.calibrate_from_window(t)
    assert d.baseline_window_mae is not None and d.baseline_window_mae < 0.01
    assert d.degraded and d.degraded_at_t == fired_at
    assert step_t < d.degraded_at_t <= step_t + DEGRADATION_HOLD_S + DEGRADATION_WINDOW_S
    assert d.recent_window_mae > d.thresholds()["threshold"]


def test_calibrate_accepts_samples_and_pairs():
    d = DegradationDetector(DT)
    assert d.calibrate([0.01] * 500) == pytest.approx(0.01)
    assert d.calibrate([(0.62, 0.6)] * 10) == pytest.approx(0.02)
    with pytest.raises(ValueError):
        d.calibrate([])


def test_no_fire_before_calibration():
    d = DegradationDetector(DT)
    for k in range(400):
        assert not d.update(k * DT, 0.0, 0.6)


def test_override_trips_after_calibration():
    d = DegradationDetector(DT)
    d.calibrate([0.01] * 150)
    assert not d.update(0.0, 0.6, 0.6)
    assert d.update(0.1, 0.6, 0.6, override=True)
    assert d.degraded_reason == "supervisor_override"


PLANT_SEED = 5


def _rollout(scenario, duration, dist, calibrate_s, ctrl=None, **kw) -> MonitoredResult:
    return run_monitored_rollout(TankSimulator(), ctrl or PIDController(), Supervisor(), duration_s=duration,
                                 target=0.6, seed=PLANT_SEED, scenario=scenario, disturbance=dist,
                                 calibrate_s=calibrate_s, **kw)


@pytest.fixture(scope="module")
def nominal() -> MonitoredResult:
    return _rollout(5, 120.0, None, 60.0)


@pytest.fixture(scope="module")
def pump_derate() -> MonitoredResult:
    return _rollout(2000, 180.0, DisturbanceSpec(family="pump_derate", at_t=60.0), 60.0)


def test_quiet_on_nominal_pid(nominal):
    print("\nnominal plant 5:", nominal.detector_state)
    assert nominal.degraded_at_t is None
    assert nominal.post_trace is None
    assert len(nominal.pre_trace.steps) == len(nominal.trace.steps) == 1200


def test_quiet_when_pid_rejects_pump_derate(pump_derate):
    print("\npump_derate plant 5 / scenario 2000:", pump_derate.detector_state)
    assert pump_derate.degraded_at_t is None, pump_derate.detector_state
    assert pump_derate.trace.disturbance_at == 60.0
    assert pump_derate.trace.meta["seed"] == PLANT_SEED and pump_derate.trace.meta["scenario"] == 2000


def test_rollout_matches_run_episode(pump_derate):
    from backend.controller.runtime import run_episode

    ref = run_episode(TankSimulator(), PIDController(), Supervisor(), 180.0, 0.6, PLANT_SEED, scenario=2000,
                      disturbance=DisturbanceSpec(family="pump_derate", at_t=60.0))
    assert [s.model_dump() for s in ref.steps] == [s.model_dump() for s in pump_derate.trace.steps]


def test_detects_and_splits_traces():
    # A constant 0.3 duty cannot hold the target: error is large; calibrate at 30 s on a nominal
    # PID would be ideal, but here we just check the split mechanics with a hand-calibrated detector.
    det = DegradationDetector(DT)
    det.calibrate([0.005] * 150)
    r = _rollout(5, 120.0, None, 0.0, ctrl=ConstantController(0.3), detector=det, stop_after_detection_s=5.0)
    assert r.degraded_at_t is not None
    t_deg = r.degraded_at_t
    assert r.trace.steps[-1].t == pytest.approx(t_deg + 5.0)
    assert all(s.t < t_deg for s in r.pre_trace.steps)
    assert r.post_trace is not None
    assert r.post_trace.steps[0].t == pytest.approx(max(0.0, t_deg - DEGRADATION_WINDOW_S), abs=1e-6)
    json.loads(r.model_dump_json())


def test_calibrate_after_disturbance_rejected():
    with pytest.raises(ValueError):
        _rollout(5, 10.0, DisturbanceSpec(family="pump_derate", at_t=5.0), 6.0)
