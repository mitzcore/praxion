"""Trusted fixed-rate control loop around a controller, under the safety supervisor.

Imports only trusted modules. The controller is called only via reset() / step().
"""
from __future__ import annotations

import math

from backend.controller.protocol import Controller
from backend.plant.base import PlantAdapter
from backend.safety.supervisor import Supervisor
from backend.schemas import DisturbanceSpec, Trace, TraceStep

_TRIP_REASONS = ("interlock_high", "hard_cutoff")


def _apply(plant: PlantAdapter, u_applied: float, reason: str) -> None:
    """Step the plant; on an interlock / hard-cutoff trip also cut pump power and close the inlet
    (plant.emergency_stop flushes any commands queued in the actuator delay line)."""
    plant.step(u_applied)
    if reason.startswith(_TRIP_REASONS):
        plant.emergency_stop()


def _n_ticks(duration_s: float, dt: float) -> int:
    return max(0, round(duration_s / dt))


def run_episode(
    plant: PlantAdapter,
    controller: Controller,
    supervisor: Supervisor,
    duration_s: float,
    target: float,
    seed: int,
    scenario: int | None = None,
    disturbance: DisturbanceSpec | None = None,
    close_after: bool = False,
) -> Trace:
    """Reset plant (machine `seed`, episode `scenario`, default = seed) and controller, then run
    `duration_s` of closed-loop control.

    Any exception raised by controller.step is caught and treated as a NaN request; the tick's
    reason becomes "controller_exception:<ExceptionType>" (the supervisor applies the fallback).
    The caller owns the controller lifecycle; pass close_after=True to close it at the end.
    """
    plant.reset(seed, scenario)
    if disturbance is not None:
        plant.schedule_disturbance(disturbance)
    controller.reset()
    dt = plant.dt
    steps: list[TraceStep] = []
    try:
        for _ in range(_n_ticks(duration_s, dt)):
            obs = plant.observe()
            exc_reason: str | None = None
            try:
                u_req = float(
                    controller.step({"y": obs.y, "target": target, "dt": dt, "elapsed_s": obs.t})
                )
            except Exception as exc:  # noqa: BLE001 - any controller failure is contained
                u_req = math.nan
                exc_reason = f"controller_exception:{type(exc).__name__}"
            decision = supervisor.filter(u_req, obs, now_t=obs.t)
            h_true = float(plant.true_state()["h_true"])
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
    finally:
        if close_after:
            controller.close()
    return Trace(
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
        },
    )


def run_constant_input(
    plant: PlantAdapter, supervisor: Supervisor, u: float, duration_s: float, target: float
) -> Trace:
    """Apply a constant request `u` through the supervisor for `duration_s` (exploration).

    Does NOT reset the plant: continues from its current state.
    """
    dt = plant.dt
    steps: list[TraceStep] = []
    for _ in range(_n_ticks(duration_s, dt)):
        obs = plant.observe()
        decision = supervisor.filter(u, obs, now_t=obs.t)
        h_true = float(plant.true_state()["h_true"])
        _apply(plant, decision.u_applied, decision.reason)
        steps.append(
            TraceStep(
                t=obs.t,
                y=obs.y,
                h_true=h_true,
                u_requested=float(u),
                u_applied=decision.u_applied,
                override=decision.override,
                reason=decision.reason,
            )
        )
    return Trace(steps=steps, dt=dt, target=target, meta={"kind": "constant_input", "u": float(u)})
