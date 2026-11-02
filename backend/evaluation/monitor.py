"""Trusted degradation monitor for a deployed controller (plan section 6.8).

Runs ONLINE, so it only ever looks at the measured (noisy) ``y`` and the target, never at
``h_true``. Thresholds come from the frozen ``evaluation/config.py`` and are exposed through
``DegradationDetector.thresholds()`` for logging and the UI.

Rule: rolling ``window_s`` MAE of |y - target| exceeds ``max(factor * baseline, floor)`` for
``hold_s`` continuous seconds, or any supervisor override occurs after calibration.

Plant-agnostic: window / hold / factor / floor and the target come from a ``PlantProfile``
(TANK, i.e. the frozen config values, when none is given).
"""
from __future__ import annotations

import math
import sys
from collections import deque
from collections.abc import Callable, Iterable, Sequence
from typing import Any

from pydantic import BaseModel

from backend.controller.protocol import Controller
from backend.controller.runtime import _apply
from backend.evaluation.config import (
    DEGRADATION_FACTOR,
    DEGRADATION_FLOOR,
    DEGRADATION_HOLD_S,
    DEGRADATION_WINDOW_S,
)
from backend.plant.base import PlantAdapter
from backend.profiles import TANK, PlantProfile
from backend.safety.supervisor import Supervisor
from backend.schemas import DisturbanceSpec, Trace, TraceStep

_EPS = 1e-9


def _n_ticks(duration_s: float, dt: float) -> int:
    return max(0, round(duration_s / dt))


class DegradationDetector:
    """Rolling-window MAE detector on measured y.

    Call ``calibrate()`` on a nominal segment first; ``update()`` before calibration only fills
    the rolling window and never declares degradation.
    """

    def __init__(
        self,
        dt: float,
        window_s: float | None = None,
        factor: float | None = None,
        floor: float | None = None,
        hold_s: float | None = None,
        *,
        profile: PlantProfile | None = None,
    ) -> None:
        """Explicit keyword values win; otherwise the profile's monitor_* values; otherwise the frozen
        config (tank) values DEGRADATION_WINDOW_S / _FACTOR / _FLOOR / _HOLD_S."""
        if profile is not None:
            window_s = profile.monitor_window_s if window_s is None else window_s
            factor = profile.monitor_factor if factor is None else factor
            floor = profile.monitor_floor if floor is None else floor
            hold_s = profile.monitor_hold_s if hold_s is None else hold_s
        window_s = DEGRADATION_WINDOW_S if window_s is None else window_s
        factor = DEGRADATION_FACTOR if factor is None else factor
        floor = DEGRADATION_FLOOR if floor is None else floor
        hold_s = DEGRADATION_HOLD_S if hold_s is None else hold_s
        if dt <= 0:
            raise ValueError("dt must be > 0")
        self.dt = float(dt)
        self.window_s = float(window_s)
        self.factor = float(factor)
        self.floor = float(floor)
        self.hold_s = float(hold_s)
        self._n = max(1, round(self.window_s / self.dt))
        self._win: deque[float] = deque(maxlen=self._n)
        self._sum = 0.0
        self.baseline_window_mae: float | None = None
        self.recent_window_mae: float | None = None
        self.degraded = False
        self.degraded_at_t: float | None = None
        self.degraded_reason: str | None = None
        self._above_since: float | None = None
        self.calibrated_at_t: float | None = None

    @classmethod
    def from_profile(cls, profile: PlantProfile, dt: float | None = None) -> DegradationDetector:
        return cls(profile.dt if dt is None else dt, profile=profile)

    # ------------------------------------------------------------------ calibration
    def calibrate(self, samples: Trace | Iterable[float] | Iterable[Sequence[float]]) -> float:
        """Set the baseline from the LAST window of a nominal segment.

        Accepts a Trace (uses measured ``y`` vs ``trace.target``), an iterable of absolute
        errors, or an iterable of ``(y, target)`` pairs. Returns the baseline window MAE.
        """
        if isinstance(samples, Trace):
            errs = [abs(s.y - samples.target) for s in samples.steps]
            if samples.steps:
                self.calibrated_at_t = samples.steps[-1].t
        else:
            errs = []
            for s in samples:
                if isinstance(s, (int, float)):
                    errs.append(abs(float(s)))
                else:
                    y, target = s[0], s[1]
                    errs.append(abs(float(y) - float(target)))
        errs = [e for e in errs if math.isfinite(e)][-self._n:]
        if not errs:
            raise ValueError("calibration segment is empty")
        self.baseline_window_mae = float(sum(errs) / len(errs))
        return self.baseline_window_mae

    def calibrate_from_window(self, t: float | None = None) -> float:
        """Calibrate on the detector's own current rolling window (the window ending now)."""
        if not self._win:
            raise ValueError("no samples in window to calibrate on")
        self.baseline_window_mae = self._sum / len(self._win)
        self.calibrated_at_t = t
        return self.baseline_window_mae

    @property
    def calibrated(self) -> bool:
        return self.baseline_window_mae is not None

    def threshold(self) -> float | None:
        """Current trip level, or None before calibration."""
        if self.baseline_window_mae is None:
            return None
        return max(self.factor * self.baseline_window_mae, self.floor)

    def thresholds(self) -> dict:
        """Config and live values for logging / UI."""
        return {
            "window_s": self.window_s,
            "factor": self.factor,
            "floor": self.floor,
            "hold_s": self.hold_s,
            "baseline_window_mae": self.baseline_window_mae,
            "threshold": self.threshold(),
        }

    # ------------------------------------------------------------------ online update
    def update(self, t: float, y: float, target: float, override: bool = False) -> bool:
        """Feed one measured sample. Returns ``degraded`` (latched once True)."""
        e = abs(float(y) - float(target))
        if not math.isfinite(e):
            e = 1.0  # invalid reading counts as maximal error
        if len(self._win) == self._win.maxlen:
            self._sum -= self._win[0]
        self._win.append(e)
        self._sum += e
        self.recent_window_mae = self._sum / len(self._win)
        if self.degraded or not self.calibrated:
            return self.degraded
        if override:
            self._trip(t, "supervisor_override")
            return True
        thr = self.threshold()
        assert thr is not None
        full = len(self._win) == self._win.maxlen
        if full and self.recent_window_mae > thr:
            if self._above_since is None:
                self._above_since = float(t)
            if float(t) - self._above_since >= self.hold_s - _EPS:
                self._trip(t, f"window_mae>{thr:.4f} for {self.hold_s:.0f}s")
        else:
            self._above_since = None
        return self.degraded

    def _trip(self, t: float, reason: str) -> None:
        self.degraded = True
        self.degraded_at_t = float(t)
        self.degraded_reason = reason

    def state(self) -> dict:
        """Serializable snapshot (trusted logs / UI)."""
        return {
            **self.thresholds(),
            "recent_window_mae": self.recent_window_mae,
            "degraded": self.degraded,
            "degraded_at_t": self.degraded_at_t,
            "degraded_reason": self.degraded_reason,
            "calibrated_at_t": self.calibrated_at_t,
        }


class MonitoredResult(BaseModel):
    """Outcome of a monitored rollout. All traces are TRUSTED (contain h_true / meta)."""

    trace: Trace
    detector_state: dict
    degraded_at_t: float | None
    pre_trace: Trace
    post_trace: Trace | None


# Returns None to block until the operator is done (the loop pauses), or a zero-argument callable that
# reports whether the operator has finished: then the control loop keeps running while the operator
# works (on hardware the heater must stay under control), and the first tick at which it returns True
# is recorded as the disturbance time.
OperatorPause = Callable[[], Any]


def terminal_operator_pause(prompt: str = "Apply the physical disturbance now, then press Enter to resume... ") -> None:
    """Default operator hook: print a prompt and wait for Enter when stdin is a terminal; no-op otherwise
    (CI, batch runs, piped stdin)."""
    try:
        interactive = sys.stdin is not None and sys.stdin.isatty()
    except (AttributeError, ValueError):
        interactive = False
    if not interactive:
        return
    print(prompt, end="", flush=True)
    try:
        input()
    except EOFError:
        pass


def _sub_trace(trace: Trace, steps: list[TraceStep]) -> Trace:
    return Trace(steps=steps, dt=trace.dt, target=trace.target, disturbance_at=trace.disturbance_at,
                 meta=dict(trace.meta))


def run_monitored_rollout(
    plant: PlantAdapter,
    controller: Controller,
    supervisor: Supervisor,
    *,
    duration_s: float,
    target: float | None = None,
    seed: int,
    scenario: int | None = None,
    disturbance: DisturbanceSpec | None,
    calibrate_s: float | None = None,
    detector: DegradationDetector | None = None,
    stop_after_detection_s: float | None = None,
    profile: PlantProfile | None = None,
    pause_for_operator: OperatorPause | None = None,
    disturbance_at_s: float | None = None,
) -> MonitoredResult:
    """Deployed-controller rollout with online degradation detection.

    Mirrors ``runtime.run_episode`` tick for tick (exception containment, supervisor, h_true
    recording) and additionally feeds each measured sample to the detector. The detector is
    calibrated on the window ending at ``calibrate_s``, which must precede any disturbance.
    ``seed`` picks the machine, ``scenario`` (default: ``seed``) the episode, as in run_episode.
    The caller owns the controller lifecycle (it is not closed here).

    ``profile`` (TANK when None) supplies the default ``target``, ``calibrate_s`` and detector settings.
    ``schedule_disturbance`` is only called when ``disturbance`` is given, so a physical plant whose
    ``schedule_disturbance`` raises NotImplementedError works with ``disturbance=None``.
    ``pause_for_operator`` (optional) is called exactly once, when the rollout time first reaches
    ``disturbance_at_s`` (default: ``profile.monitor_pre_s``, the live rollout's change time, which
    follows ``monitor_calibrate_s``; the evaluator suites use ``profile.disturbance_at_s`` instead), so a human can apply a physical
    disturbance. It may block; the rollout clock is the plant's own time, so wall time spent in the hook
    is not counted: the next tick simply resumes from a fresh observation.
    """
    prof = profile or TANK
    if target is None:
        target = prof.target
    if calibrate_s is None:
        calibrate_s = prof.monitor_calibrate_s
    pause_at: float | None = None
    if pause_for_operator is not None:
        pause_at = prof.monitor_pre_s if disturbance_at_s is None else float(disturbance_at_s)
    if disturbance is not None and calibrate_s > disturbance.at_t + _EPS:
        raise ValueError(f"calibrate_s={calibrate_s} must not be after the disturbance at {disturbance.at_t}")
    if pause_at is not None and calibrate_s > pause_at + _EPS:
        raise ValueError(f"calibrate_s={calibrate_s} must not be after the operator disturbance at {pause_at}")
    plant.reset(seed, scenario)
    if disturbance is not None:
        plant.schedule_disturbance(disturbance)
    controller.reset()
    dt = plant.dt
    det = detector or DegradationDetector(dt, profile=prof)
    steps: list[TraceStep] = []
    stop_t: float | None = None
    paused = False
    operator_t: float | None = None
    waiter: Callable[[], Any] | None = None
    for _ in range(_n_ticks(duration_s, dt)):
        obs = plant.observe()
        if pause_at is not None and not paused and obs.t >= pause_at - dt / 2:
            paused = True
            assert pause_for_operator is not None
            ret = pause_for_operator()
            if callable(ret):
                waiter = ret  # non-blocking: control continues while the operator applies the change
            else:
                operator_t = obs.t
                obs = plant.observe()  # fresh reading after the (possibly long) pause
        if waiter is not None and operator_t is None and waiter():
            operator_t = obs.t
            waiter = None
        exc_reason: str | None = None
        try:
            u_req = float(controller.step({"y": obs.y, "target": target, "dt": dt, "elapsed_s": obs.t}))
        except Exception as exc:  # noqa: BLE001 - any controller failure is contained
            u_req = math.nan
            exc_reason = f"controller_exception:{type(exc).__name__}"
        decision = supervisor.filter(u_req, obs, now_t=obs.t)
        h_true = float(plant.true_state()["h_true"])
        # Same path as run_episode: on an interlock / hard-cutoff trip the plant's emergency stop also
        # flushes commands queued in the actuator delay line (audit 2026-11-02: plant.step alone let
        # up to 20 s of queued pump commands keep filling the tank after a trip).
        _apply(plant, decision.u_applied, decision.reason)
        steps.append(
            TraceStep(
                t=obs.t,
                y=obs.y,
                h_true=h_true,
                u_requested=u_req,
                u_applied=decision.u_applied,
                override=decision.override,
                reason=exc_reason or decision.reason,
            )
        )
        was_degraded = det.degraded
        det.update(obs.t, obs.y, target, override=decision.override)
        if not det.calibrated and obs.t >= calibrate_s - dt / 2:
            det.calibrate_from_window(obs.t)
        if det.degraded and not was_degraded and stop_after_detection_s is not None:
            stop_t = obs.t + stop_after_detection_s
        if stop_t is not None and obs.t >= stop_t - _EPS:
            break
    trace = Trace(
        steps=steps,
        dt=dt,
        target=target,
        disturbance_at=disturbance.at_t if disturbance is not None else operator_t,
        meta={
            "seed": seed,
            "scenario": seed if scenario is None else scenario,
            "controller": getattr(controller, "name", "?"),
            "isolation": getattr(controller, "isolation", "?"),
            "disturbance": disturbance.model_dump() if disturbance is not None else None,
            "duration_s": duration_s,
            "kind": "monitored_rollout",
            "detector": det.thresholds(),
        },
    )
    # Extra meta only off the tank path, so recorded tank traces stay byte-identical.
    if prof.name != "tank":
        trace.meta["profile"] = prof.name
    if operator_t is not None:
        trace.meta["operator_disturbance_at_s"] = operator_t
    t_deg = det.degraded_at_t
    if t_deg is None:
        pre, post = _sub_trace(trace, list(steps)), None
    else:
        pre = _sub_trace(trace, [s for s in steps if s.t < t_deg - _EPS])
        post = _sub_trace(trace, [s for s in steps if s.t >= t_deg - det.window_s - _EPS])
    return MonitoredResult(trace=trace, detector_state=det.state(), degraded_at_t=t_deg, pre_trace=pre,
                           post_trace=post)
