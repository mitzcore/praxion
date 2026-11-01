"""Trusted safety supervisor: final authority over u_applied (plan section 9)."""
from __future__ import annotations

import math
from typing import TYPE_CHECKING

from pydantic import BaseModel

from backend.safety.envelope import MAX_RATE_AT_FULL_DUTY, worst_case_level
from backend.schemas import Observation, ProposalVerdict, SupervisorDecision

if TYPE_CHECKING:
    from backend.profiles import PlantProfile


class SafetyLimits(BaseModel):
    """Safety envelope. Trusted; the agent may be told these values but can never change them."""

    u_min: float = 0.0
    u_max: float = 1.0
    soft_high_limit: float = 0.85
    hard_cutoff: float = 0.90
    sensor_timeout_s: float = 3.0
    max_single_experiment_s: float = 20.0
    safe_fallback_u: float = 0.0
    worst_case_rate_per_unit_u: float = MAX_RATE_AT_FULL_DUTY  # envelope rise rate at u = 1 (normalized / s)

    @classmethod
    def from_profile(cls, profile: PlantProfile) -> SafetyLimits:
        """Limits for a plant profile. ``from_profile(TANK)`` equals ``SafetyLimits()``."""
        return cls(
            u_min=0.0,
            u_max=1.0,
            soft_high_limit=profile.soft_high_limit,
            hard_cutoff=profile.hard_cutoff,
            max_single_experiment_s=profile.max_single_experiment_s,
            worst_case_rate_per_unit_u=profile.worst_case_rate_per_unit_u,
        )


class Supervisor:
    """Filters every requested command and validates exploration proposals."""

    def __init__(self, limits: SafetyLimits | None = None) -> None:
        self.limits = limits or SafetyLimits()
        self.override_count = 0
        self.violation_count = 0

    def reset_counters(self) -> None:
        """Zero the override / violation counters (e.g. at the start of an episode)."""
        self.override_count = 0
        self.violation_count = 0

    def _fallback(self, reason: str) -> SupervisorDecision:
        self.override_count += 1
        return SupervisorDecision(u_applied=self.limits.safe_fallback_u, override=True, reason=reason)

    def filter(
        self, u_requested: float, obs: Observation | None, now_t: float, estop: bool = False
    ) -> SupervisorDecision:
        """Decide the applied command. Safe fallback on e-stop, missing sensor, interlock trip,
        invalid/stale sensor, non-finite request, or measured level at/above the hard cutoff
        (second layer); else clamp. The caller (runtime) cuts the pump on interlock/hard-cutoff."""
        lim = self.limits
        if obs is not None and (obs.interlock_high or (math.isfinite(obs.y) and obs.y >= lim.hard_cutoff)):
            self.violation_count += 1
        if estop:
            return self._fallback("estop")
        if obs is None:
            return self._fallback("sensor_missing")
        # Layer 1: independent high-level interlock (binary switch, not the analog sensor).
        if obs.interlock_high:
            return self._fallback("interlock_high")
        if not math.isfinite(obs.y):
            return self._fallback("sensor_invalid")
        if (now_t - obs.t) > lim.sensor_timeout_s:
            return self._fallback(f"sensor_stale:{now_t - obs.t:.2f}s>{lim.sensor_timeout_s}s")
        try:
            u = float(u_requested)
        except (TypeError, ValueError):
            u = math.nan
        if not math.isfinite(u):
            return self._fallback("non_finite_request")
        if obs.y >= lim.hard_cutoff:
            return self._fallback(f"hard_cutoff:y={obs.y:.4f}>={lim.hard_cutoff}")
        clamped = min(max(u, lim.u_min), lim.u_max)
        if clamped != u:
            self.override_count += 1
            return SupervisorDecision(u_applied=clamped, override=True, reason="clamped")
        return SupervisorDecision(u_applied=u, override=False, reason="ok")

    def validate_proposal(
        self, u: float, duration_s: float, obs: Observation | None, dt: float = 0.1
    ) -> ProposalVerdict:
        """Approve or reject a bounded constant-input experiment. Approved values are unchanged."""
        lim = self.limits

        def reject(reason: str) -> ProposalVerdict:
            return ProposalVerdict(ok=False, reason=reason, u=None, duration_s=None)

        try:
            u_f, d_f = float(u), float(duration_s)
        except (TypeError, ValueError):
            return reject("non_numeric_proposal")
        if not math.isfinite(u_f):
            return reject("non_finite_u")
        if not math.isfinite(d_f):
            return reject("non_finite_duration")
        if u_f < lim.u_min or u_f > lim.u_max:
            return reject(f"u {u_f} outside [{lim.u_min}, {lim.u_max}]")
        if d_f <= 0:
            return reject(f"duration {d_f} must be > 0")
        if d_f > lim.max_single_experiment_s:
            return reject(f"duration {d_f} exceeds max_single_experiment_s {lim.max_single_experiment_s}")
        if obs is None or not math.isfinite(obs.y):
            return reject("no_valid_observation")
        bound = worst_case_level(obs.y, u_f, d_f, dt, lim.worst_case_rate_per_unit_u)
        # A proposal that cannot raise the level (u == 0, so bound == y) is always approvable: draining is
        # the safest action and must never be refused merely because the level is already high.
        if bound >= lim.soft_high_limit and bound > obs.y + 1e-12:
            return reject(f"worst-case bound {bound:.3f} >= soft limit {lim.soft_high_limit}")
        return ProposalVerdict(ok=True, reason=f"approved; worst-case bound {bound:.3f}", u=u, duration_s=duration_s)
