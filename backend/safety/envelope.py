"""Conservative worst-case forward bound for exploration proposals (plan section 6.4).

Deliberately crude, trusted model: maximum plausible inflow, zero outflow, no actuator lag,
no deadband. MAX_RATE_AT_FULL_DUTY is chosen to upper-bound the simulator's
pump_gain / tank_area over its whole sampling range (enforced by a test), so the bound
over-predicts the true rise. It does not account for sensor noise in `y_now`; the gap
between soft_high_limit (0.85) and hard_cutoff (0.90) is the margin for that.
"""
from __future__ import annotations

import math

# Level units per second at u = 1, scaled linearly with u. TRUSTED CONFIG. This is the tank's value
# (PlantProfile TANK.worst_case_rate_per_unit_u); other plants pass their own rate explicitly.
MAX_RATE_AT_FULL_DUTY = 0.10


def worst_case_level(
    y_now: float, u: float, duration_s: float, dt: float, rate_per_unit_u: float = MAX_RATE_AT_FULL_DUTY
) -> float:
    """Upper bound on the (normalized) output after holding `u` for `duration_s` starting from `y_now`.

    `rate_per_unit_u` is the worst-case rise rate (normalized units per second) at u = 1; it scales
    linearly with u. Integrates on the same `dt` grid as the plant (rounding the step count up).
    Pure function. Returns +inf for non-finite inputs so callers reject them.
    """
    vals = (y_now, u, duration_s, dt, rate_per_unit_u)
    if not all(math.isfinite(float(v)) for v in vals) or dt <= 0:
        return math.inf
    n_steps = max(0, math.ceil(duration_s / dt - 1e-9))
    rate = float(rate_per_unit_u) * max(0.0, float(u))
    return float(y_now) + rate * n_steps * dt
