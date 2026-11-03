"""Plant-agnostic evaluator, monitor and safety limits (backend/profiles.py consumers).

The TANK profile must reproduce the frozen constants exactly (bit-identical benchmarks); the TCLAB
profile must drive the same code with its own timings and limits.
"""
from __future__ import annotations

import math

import numpy as np
import pytest

from backend.evaluation import config as C
from backend.evaluation.baselines import ConstantController
from backend.evaluation.metrics import HARD_CUTOFF, adaptation_latency, compute_metrics
from backend.evaluation.monitor import DegradationDetector, run_monitored_rollout, terminal_operator_pause
from backend.evaluation.suite import evaluate_disturbance, evaluate_heldout
from backend.plant.base import PlantAdapter
from backend.profiles import TANK, TCLAB
from backend.safety.envelope import MAX_RATE_AT_FULL_DUTY, worst_case_level
from backend.safety.supervisor import SafetyLimits, Supervisor
from backend.schemas import DisturbanceSpec, Observation, Trace, TraceStep


# --------------------------------------------------------------------------- fake plant
class FirstOrderPlant(PlantAdapter):
    """y' = (gain * u - y) / tau, dt = 1.0 s, deterministic small seeded noise. Physical-plant stand-in:
    ``schedule_disturbance`` raises NotImplementedError unless ``allow_disturbance`` is set."""

    def __init__(self, gain: float = 1.0, tau: float = 30.0, allow_disturbance: bool = False) -> None:
        self.gain, self.tau, self.allow_disturbance = gain, tau, allow_disturbance
        self._t, self._y = 0.0, 0.0
        self._rng = np.random.default_rng(0)
        self._dist: DisturbanceSpec | None = None
        self.reset_calls = 0

    @property
    def dt(self) -> float:
        return 1.0

    def reset(self, seed: int, scenario: int | None = None) -> Observation:
        self.reset_calls += 1
        self._t = 0.0
        self._y = 0.01 * ((scenario if scenario is not None else seed) % 5)  # scenario-dependent start
        self._rng = np.random.default_rng(scenario if scenario is not None else seed)
        self._dist = None
        return self.observe()

    def observe(self) -> Observation:
        return Observation(t=self._t, y=self._y + float(self._rng.normal(0, 1e-4)))

    def step(self, u_applied: float) -> Observation:
        u = float(u_applied)
        if not math.isfinite(u) or not 0.0 <= u <= 1.0:
            raise ValueError("bad u")
        gain = self.gain
        if self._dist is not None and self._t >= self._dist.at_t:
            gain *= 0.5
        self._y += (gain * u - self._y) / self.tau * self.dt
        self._t = round(self._t + self.dt, 6)
        return self.observe()

    def true_state(self) -> dict:
        return {"h_true": self._y, "t": self._t}

    def public_description(self) -> str:
        return "first-order test plant"

    def schedule_disturbance(self, spec: DisturbanceSpec) -> None:
        if not self.allow_disturbance:
            raise NotImplementedError("physical plant: disturbances are applied by the operator")
        self._dist = spec

    def emergency_stop(self) -> None:
        pass


# --------------------------------------------------------------------------- profiles / limits
def test_tank_profile_reproduces_frozen_constants():
    assert (TANK.target, TANK.band, TANK.episode_s, TANK.settle_s) == (C.TARGET, C.BAND, C.EPISODE_S, C.SETTLE_S)
    assert (TANK.disturbance_at_s, TANK.disturbance_episode_s) == (C.DISTURBANCE_AT_S, C.DISTURBANCE_EPISODE_S)
    assert TANK.worst_case_rate_per_unit_u == MAX_RATE_AT_FULL_DUTY
    assert TANK.hard_cutoff == HARD_CUTOFF
    assert SafetyLimits.from_profile(TANK) == SafetyLimits()


def test_safety_limits_from_tclab_profile():
    lim = SafetyLimits.from_profile(TCLAB)
    assert (lim.u_min, lim.u_max) == (0.0, 1.0)
    assert lim.soft_high_limit == 0.85 and lim.hard_cutoff == 0.90
    assert lim.max_single_experiment_s == 180.0
    assert lim.worst_case_rate_per_unit_u == 0.006


def test_worst_case_level_takes_rate():
    assert worst_case_level(0.2, 1.0, 180.0, 1.0, 0.006) == pytest.approx(0.2 + 1.08)
    assert worst_case_level(0.2, 1.0, 5.0, 0.1) == pytest.approx(0.2 + MAX_RATE_AT_FULL_DUTY * 5.0)  # default = tank


def test_validate_proposal_uses_limit_rate():
    obs = Observation(t=0.0, y=0.10)
    tclab = Supervisor(SafetyLimits.from_profile(TCLAB))
    ok = tclab.validate_proposal(1.0, 100.0, obs, dt=1.0)  # 0.10 + 0.6 = 0.70 < 0.85
    assert ok.ok, ok.reason
    bad = tclab.validate_proposal(1.0, 180.0, obs, dt=1.0)  # 0.10 + 1.08 >= 0.85
    assert not bad.ok and "worst-case bound" in bad.reason
    assert not tclab.validate_proposal(0.5, 181.0, obs, dt=1.0).ok  # max_single_experiment_s = 180


# --------------------------------------------------------------------------- metrics
def _trace(hs: list[float], dt: float = 1.0, target: float = 0.5, disturbance_at: float | None = None) -> Trace:
    steps = [TraceStep(t=i * dt, y=h, h_true=h, u_requested=0.5, u_applied=0.5, override=False, reason="ok")
             for i, h in enumerate(hs)]
    return Trace(steps=steps, dt=dt, target=target, disturbance_at=disturbance_at)


def test_metrics_band_sustain_and_cutoff_parameters():
    tr = _trace([0.5] * 10 + [0.95] * 2 + [0.5] * 20, disturbance_at=5.0)
    m_default = compute_metrics(tr, 0.0)
    assert m_default.hard_violations == 2
    assert compute_metrics(tr, 0.0, hard_cutoff=0.99).hard_violations == 0
    assert compute_metrics(tr, 0.0, band=(0.45, 0.55)).in_band_fraction == pytest.approx(30 / 32)
    assert compute_metrics(tr, 0.0, band=(0.0, 0.1)).in_band_fraction == 0.0
    # default band (0.55, 0.65) excludes 0.5 entirely → latency None; custom band → final run starts at 12 s
    assert adaptation_latency(tr) is None
    assert adaptation_latency(tr, band=(0.45, 0.55)) == pytest.approx(12.0 - 5.0)
    assert adaptation_latency(tr, band=(0.45, 0.55), sustain_s=25.0) is None


# --------------------------------------------------------------------------- suite
def _const_for_target() -> ConstantController:
    return ConstantController(TCLAB.target, name="const_target")


def test_tclab_heldout_runs_end_to_end_on_fake_plant():
    rep = evaluate_heldout(_const_for_target, candidate_id="fake-v1", plant_seed=1, profile=TCLAB,
                           plant_factory=FirstOrderPlant)
    assert len(rep.episodes) == 10
    assert all(e.metrics.steps == 900 for e in rep.episodes)
    assert [e.seed for e in rep.episodes] == C.HELDOUT_SEEDS
    assert all(e.metrics.scored_steps == 600 for e in rep.episodes)  # scored after settle_s = 300 s
    assert all(e.trace.target == pytest.approx(TCLAB.target) for e in rep.episodes)
    assert rep.gate_passed and rep.aggregate["n_passed"] == 10.0
    assert "after 300 s" in rep.gate_reasons[0]
    assert rep.comparison["baseline_pid"]["name"] == "baseline_pid (tank tuning)"
    assert rep.comparison["baseline_onoff"]["name"] == "baseline_onoff (tank tuning)"
    assert "baseline_pid_n_passed" in rep.aggregate


def test_tclab_disturbance_suite_uses_profile_timing():
    rep = evaluate_disturbance(_const_for_target, "pump_derate", candidate_id="fake-v1", plant_seed=1, profile=TCLAB,
                               plant_factory=lambda: FirstOrderPlant(allow_disturbance=True))
    assert len(rep.episodes) == len(C.DISTURBANCE_SEEDS)
    e = rep.episodes[0]
    assert e.metrics.steps == 1200 and e.trace.disturbance_at == 400.0
    assert e.metrics.scored_steps == 1200 - 700  # scored from disturbance_at_s + settle_s
    assert rep.comparison["baseline_pid"]["name"] == "baseline_pid (tank tuning)"


# --------------------------------------------------------------------------- monitor
def test_detector_profile_defaults():
    d = DegradationDetector(1.0, profile=TCLAB)
    th = d.thresholds()
    assert (th["window_s"], th["hold_s"], th["factor"], th["floor"]) == (60.0, 30.0, 2.0, 0.02)
    assert DegradationDetector.from_profile(TCLAB).dt == 1.0
    t = DegradationDetector(0.1).thresholds()
    assert (t["window_s"], t["hold_s"], t["floor"]) == (C.DEGRADATION_WINDOW_S, C.DEGRADATION_HOLD_S, C.DEGRADATION_FLOOR)
    assert DegradationDetector(1.0, window_s=10.0, profile=TCLAB).window_s == 10.0  # explicit wins


def test_tclab_detector_calibrates_at_profile_time_and_fires_on_step():
    rng = np.random.default_rng(0)
    d = DegradationDetector(1.0, profile=TCLAB)
    target, fired_at = TCLAB.target, None
    for k in range(int(TCLAB.monitor_pre_s) + 300):
        t = float(k)
        y = target + rng.normal(0, 0.003) + (0.08 if t >= TCLAB.monitor_pre_s else 0.0)
        d.update(t, y, target)
        if not d.calibrated and t >= TCLAB.monitor_calibrate_s - 0.5:
            d.calibrate_from_window(t)
        if d.degraded and fired_at is None:
            fired_at = t
    assert d.calibrated_at_t == TCLAB.monitor_calibrate_s
    pre = TCLAB.monitor_pre_s
    assert fired_at is not None and pre < fired_at <= pre + TCLAB.monitor_window_s + TCLAB.monitor_hold_s


def test_monitored_rollout_physical_plant_operator_pause():
    plant = FirstOrderPlant()  # schedule_disturbance raises NotImplementedError
    calls: list[float] = []

    def pause() -> None:
        calls.append(plant.true_state()["t"])
        plant.gain = 0.5  # the "operator" changes the machine

    res = run_monitored_rollout(plant, ConstantController(TCLAB.target), Supervisor(SafetyLimits.from_profile(TCLAB)),
                                duration_s=TCLAB.monitor_duration_s, seed=1, disturbance=None, profile=TCLAB,
                                pause_for_operator=pause, stop_after_detection_s=TCLAB.monitor_post_detection_s)
    pre = TCLAB.monitor_pre_s
    assert calls == [pre]  # exactly once, at profile.monitor_pre_s (default)
    assert res.detector_state["calibrated_at_t"] == TCLAB.monitor_calibrate_s
    assert res.trace.target == pytest.approx(TCLAB.target)
    assert res.trace.disturbance_at == pre and res.trace.meta["operator_disturbance_at_s"] == pre
    assert res.degraded_at_t is not None and res.degraded_at_t > pre
    assert res.trace.steps[-1].t <= res.degraded_at_t + TCLAB.monitor_post_detection_s + 1e-9


def test_monitored_rollout_physical_plant_without_disturbance_or_hook():
    plant = FirstOrderPlant()
    res = run_monitored_rollout(plant, ConstantController(TCLAB.target), Supervisor(SafetyLimits.from_profile(TCLAB)),
                                duration_s=800.0, seed=1, disturbance=None, profile=TCLAB)
    assert len(res.trace.steps) == 800 and res.trace.disturbance_at is None
    assert res.degraded_at_t is None
    with pytest.raises(NotImplementedError):  # a disturbance on the physical plant must fail loudly
        run_monitored_rollout(plant, ConstantController(0.4), Supervisor(), duration_s=10.0, seed=1,
                              disturbance=DisturbanceSpec(family="pump_derate", at_t=TCLAB.monitor_pre_s), profile=TCLAB)


def test_pause_hook_explicit_time_and_calibration_order():
    plant = FirstOrderPlant()
    calls: list[float] = []
    at = TCLAB.monitor_calibrate_s + 40.0
    run_monitored_rollout(plant, ConstantController(0.4), Supervisor(), duration_s=at + 30.0, seed=1, disturbance=None,
                          profile=TCLAB, pause_for_operator=lambda: calls.append(plant.true_state()["t"]),
                          disturbance_at_s=at)
    assert calls == [at]
    with pytest.raises(ValueError):
        run_monitored_rollout(plant, ConstantController(0.4), Supervisor(), duration_s=10.0, seed=1, disturbance=None,
                              profile=TCLAB, pause_for_operator=lambda: None, disturbance_at_s=100.0)


def test_terminal_pause_is_noop_without_tty(monkeypatch):
    import io
    import sys

    monkeypatch.setattr(sys, "stdin", io.StringIO(""))
    terminal_operator_pause()  # must not block or raise


def test_operator_pause_non_blocking_keeps_control_running() -> None:
    """A pause hook that returns a callable must not stop the loop: the controller keeps stepping while
    the operator works, and the first tick at which the callable reports done is the disturbance time."""
    from backend.evaluation.monitor import run_monitored_rollout
    from backend.plant.tclab_plant import TCLabSim
    from backend.safety.supervisor import SafetyLimits, Supervisor

    plant = TCLabSim()
    sup = Supervisor(SafetyLimits.from_profile(TCLAB))

    class Ctrl:
        name = "test"
        isolation = "none"
        calls = 0

        def reset(self) -> None:
            pass

        def step(self, obs: dict) -> float:
            self.calls += 1
            return 0.4

        def close(self) -> None:
            pass

    ctrl = Ctrl()
    polls = {"n": 0}

    def pause() -> object:
        def done() -> bool:
            polls["n"] += 1
            return polls["n"] > 25  # "Enter" arrives 25 ticks after the prompt
        return done

    res = run_monitored_rollout(plant, ctrl, sup, duration_s=200.0, target=TCLAB.target, seed=1, disturbance=None,
                                calibrate_s=80.0, profile=TCLAB, pause_for_operator=pause, disturbance_at_s=100.0,
                                stop_after_detection_s=None)
    ts = [s.t for s in res.trace.steps]
    assert len(ts) == 200 and ctrl.calls == 200, "control loop paused during the operator prompt"
    op_t = res.trace.meta.get("operator_disturbance_at_s")
    assert op_t is not None and 124.0 <= op_t <= 126.0, op_t
    assert res.trace.disturbance_at == op_t


def test_orchestrator_operator_pause_without_tty_waits_for_trigger_file(monkeypatch, tmp_path):
    """Launched without a keyboard (EOF on stdin), the operator prompt must NOT count as applied: it waits for the
    trigger file in the run directory, and only then reports done."""
    import io
    import sys
    import time

    from backend.agent.orchestrator import Orchestrator

    monkeypatch.setattr(sys, "stdin", io.StringIO(""))
    events: list[dict] = []

    class Store:
        dir = tmp_path

    class Fake:
        store = Store()

        def _event(self, kind, **payload):
            events.append({"kind": kind, **payload})

    done = Orchestrator._operator_pause(Fake())
    time.sleep(0.3)
    assert done() is False, "EOF on stdin was mistaken for Enter"
    assert events[0]["mechanism"] == "trigger_file" and events[0]["trigger"] == str(tmp_path / "OPERATOR_GO")
    (tmp_path / "OPERATOR_GO").touch()
    deadline = time.time() + 5.0
    while not done() and time.time() < deadline:
        time.sleep(0.05)
    assert done() is True
