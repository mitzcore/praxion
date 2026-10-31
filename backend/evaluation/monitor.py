"""Trusted degradation monitor for a deployed controller (plan section 6.8).

Runs ONLINE, so it only ever looks at the measured (noisy) ``y`` and the target, never at
``h_true``. Thresholds come from the frozen ``evaluation/config.py`` and are exposed through
``DegradationDetector.thresholds()`` for logging and the UI.

Rule: rolling ``window_s`` MAE of |y - target| exceeds ``max(factor * baseline, floor)`` for
``hold_s`` continuous seconds, or any supervisor override occurs after calibration.
"""
from __future__ import annotations

import math
from collections import deque
from collections.abc import Iterable, Sequence

from pydantic import BaseModel

from backend.controller.protocol import Controller
from backend.evaluation.config import (
    DEGRADATION_FACTOR,
    DEGRADATION_FLOOR,
    DEGRADATION_HOLD_S,
    DEGRADATION_WINDOW_S,
)
from backend.plant.base import PlantAdapter
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
        window_s: float = DEGRADATION_WINDOW_S,
        factor: float = DEGRADATION_FACTOR,
        floor: float = DEGRADATION_FLOOR,
        hold_s: float = DEGRADATION_HOLD_S,
    ) -> None:
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


def _sub_trace(trace: Trace, steps: list[TraceStep]) -> Trace:
    return Trace(steps=steps, dt=trace.dt, target=trace.target, disturbance_at=trace.disturbance_at,
                 meta=dict(trace.meta))


def run_monitored_rollout(
    plant: PlantAdapter,
    controller: Controller,
    supervisor: Supervisor,
    *,
    duration_s: float,
    target: float,
    seed: int,
    scenario: int | None = None,
    disturbance: DisturbanceSpec | None,
    calibrate_s: float,
    detector: DegradationDetector | None = None,
    stop_after_detection_s: float | None = None,
) -> MonitoredResult:
    """Deployed-controller rollout with online degradation detection.

    Mirrors ``runtime.run_episode`` tick for tick (exception containment, supervisor, h_true
    recording) and additionally feeds each measured sample to the detector. The detector is
    calibrated on the window ending at ``calibrate_s``, which must precede any disturbance.
    ``seed`` picks the machine, ``scenario`` (default: ``seed``) the episode, as in run_episode.
    The caller owns the controller lifecycle (it is not closed here).
    """
    if disturbance is not None and calibrate_s > disturbance.at_t + _EPS:
        raise ValueError(f"calibrate_s={calibrate_s} must not be after the disturbance at {disturbance.at_t}")
    plant.reset(seed, scenario)
    if disturbance is not None:
        plant.schedule_disturbance(disturbance)
    controller.reset()
    dt = plant.dt
    det = detector or DegradationDetector(dt)
    steps: list[TraceStep] = []
    stop_t: float | None = None
    for _ in range(_n_ticks(duration_s, dt)):
        obs = plant.observe()
        exc_reason: str | None = None
        try:
            u_req = float(controller.step({"y": obs.y, "target": target, "dt": dt, "elapsed_s": obs.t}))
        except Exception as exc:  # noqa: BLE001 - any controller failure is contained
            u_req = math.nan
            exc_reason = f"controller_exception:{type(exc).__name__}"
        decision = supervisor.filter(u_req, obs, now_t=obs.t)
        h_true = float(plant.true_state()["h_true"])
        plant.step(decision.u_applied)
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
        disturbance_at=disturbance.at_t if disturbance is not None else None,
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
    t_deg = det.degraded_at_t
    if t_deg is None:
        pre, post = _sub_trace(trace, list(steps)), None
    else:
        pre = _sub_trace(trace, [s for s in steps if s.t < t_deg - _EPS])
        post = _sub_trace(trace, [s for s in steps if s.t >= t_deg - det.window_s - _EPS])
    return MonitoredResult(trace=trace, detector_state=det.state(), degraded_at_t=t_deg, pre_trace=pre,
                           post_trace=post)
