"""Shared Pydantic v2 schemas for observations, traces, safety decisions and metrics.

Trust note: `Trace` carries trusted-only data (`h_true`, `meta`). The ONLY method that may be used
to project a trace toward the agent is `Trace.agent_safe()`, which strips those fields.
"""
from __future__ import annotations

import math
from typing import Any, Literal

import numpy as np
from pydantic import BaseModel, Field

AGENT_SAFE_MAX_POINTS = 200  # hard cap; callers default to 60 for experiments, 150 for post-change evidence
AGENT_SAFE_DEFAULT_POINTS = 60
_AGENT_SAFE_KEYS = ("t", "y", "target", "u_requested", "u_applied", "override")


class Observation(BaseModel):
    """A sensor reading. `y` is the NOISY measured level in [0, 1]; never the true state.

    `interlock_high` is an independent binary high-level switch (ideal float switch), separate
    from the noisy/delayed analog path. It is a safety input for the trusted supervisor.
    """

    t: float
    y: float
    interlock_high: bool = False


class TraceStep(BaseModel):
    """One control tick, recorded by the trusted runtime.

    `h_true` is simulator truth (TRUSTED ONLY). `u_requested` may be NaN/out-of-range;
    `u_applied` is what the supervisor actually sent to the plant.
    """

    t: float
    y: float
    h_true: float
    u_requested: float
    u_applied: float
    override: bool
    reason: str


class Trace(BaseModel):
    """A time series of control ticks plus episode context. `meta` is TRUSTED ONLY."""

    steps: list[TraceStep] = Field(default_factory=list)
    dt: float
    target: float
    disturbance_at: float | None = None
    meta: dict[str, Any] = Field(default_factory=dict)

    def times(self) -> np.ndarray:
        """Tick times in simulated seconds."""
        return np.array([s.t for s in self.steps], dtype=float)

    def y(self) -> np.ndarray:
        """Noisy measured levels."""
        return np.array([s.y for s in self.steps], dtype=float)

    def h_true(self) -> np.ndarray:
        """TRUSTED ONLY: true simulator levels."""
        return np.array([s.h_true for s in self.steps], dtype=float)

    def u_applied(self) -> np.ndarray:
        """Actuator commands actually applied by the supervisor."""
        return np.array([s.u_applied for s in self.steps], dtype=float)

    def u_requested(self) -> np.ndarray:
        """Actuator commands requested by the controller (may contain NaN)."""
        return np.array([s.u_requested for s in self.steps], dtype=float)

    def agent_safe(self, max_points: int = AGENT_SAFE_DEFAULT_POINTS) -> list[dict[str, Any]]:
        """Downsampled projection safe to show the agent.

        Contains ONLY (t, y, target, u_requested, u_applied, override) and at most `max_points`
        points. Never includes `h_true`, `reason`, or anything from `meta`. Non-finite floats
        become None so the result is always JSON-serialisable.
        """
        max_points = max(1, min(int(max_points), AGENT_SAFE_MAX_POINTS))
        n = len(self.steps)
        if n == 0:
            return []
        stride = max(1, math.ceil(n / max_points))
        out: list[dict[str, Any]] = []
        for s in self.steps[::stride]:
            out.append(
                {
                    "t": _safe_float(s.t, 2),
                    "y": _safe_float(s.y, 4),
                    "target": _safe_float(self.target, 4),
                    "u_requested": _safe_float(s.u_requested, 4),
                    "u_applied": _safe_float(s.u_applied, 4),
                    "override": bool(s.override),
                }
            )
        assert all(tuple(p.keys()) == _AGENT_SAFE_KEYS for p in out)
        return out[:max_points]


    def measured_summary(self, tail_s: float = 30.0, band: tuple[float, float] | None = None) -> dict[str, Any]:
        """Agent-safe statistics computed ONLY from the measured y and the applied u (never h_true):
        start/end values, mean of the last `tail_s` seconds, slope over the tail, min/max, and the
        measured in-band fraction over the tail when a band is given."""
        if not self.steps:
            return {}
        t, y, u = self.times(), self.y(), self.u_applied()
        tail = t >= (t[-1] - tail_s)
        yt, ut, tt = y[tail], u[tail], t[tail]
        slope = float(np.polyfit(tt, yt, 1)[0]) if tt.size >= 3 and tt[-1] > tt[0] else 0.0
        out: dict[str, Any] = {
            "t_start": _safe_float(t[0], 1), "t_end": _safe_float(t[-1], 1),
            "y_start": _safe_float(y[0], 3), "y_end": _safe_float(y[-1], 3),
            "y_min": _safe_float(float(np.min(y)), 3), "y_max": _safe_float(float(np.max(y)), 3),
            f"y_mean_last_{int(tail_s)}s": _safe_float(float(np.mean(yt)), 3),
            f"u_mean_last_{int(tail_s)}s": _safe_float(float(np.mean(ut)), 3),
            f"y_slope_last_{int(tail_s)}s_per_s": _safe_float(slope, 4),
        }
        if band is not None:
            out[f"measured_in_band_fraction_last_{int(tail_s)}s"] = _safe_float(float(np.mean((yt >= band[0]) & (yt <= band[1]))), 2)
        return out


def _safe_float(x: float, ndigits: int) -> float | None:
    x = float(x)
    return round(x, ndigits) if math.isfinite(x) else None


class DisturbanceSpec(BaseModel):
    """A hidden plant change. `magnitude=None` lets the plant pick a seeded default."""

    family: Literal["pump_derate", "extra_leak", "drain_shift", "actuator_lag"]
    at_t: float
    magnitude: float | None = None


class SupervisorDecision(BaseModel):
    """What the trusted supervisor actually applies, and why."""

    u_applied: float
    override: bool
    reason: str


class ProposalVerdict(BaseModel):
    """Verdict on an exploration experiment proposal. Approved proposals are returned unchanged."""

    ok: bool
    reason: str
    u: float | None = None
    duration_s: float | None = None


class Metrics(BaseModel):
    """Episode metrics computed from simulator truth (see evaluation/metrics.py)."""

    mae: float
    in_band_fraction: float
    actuation_energy: float
    override_count: int
    hard_violations: int
    invalid_outputs: int
    adaptation_latency_s: float | None = None
    steps: int
    scored_steps: int = 0
