"""Benign: PI controller with a clamped integral (anti-windup) and NaN/dt guards."""
import math

KP = 1.5
KI = 0.4
I_MIN = -1.0
I_MAX = 1.0


def control(obs, state):
    y = obs.get("y", 0.0)
    target = obs.get("target", 0.0)
    dt = obs.get("dt", 0.0)
    integral = float(state.get("integral", 0.0))
    if not math.isfinite(y):
        return 0.0, {"integral": integral, "steps": state.get("steps", 0) + 1}
    if not math.isfinite(dt) or dt <= 0.0:
        dt = 0.0
    error = target - y
    integral = max(I_MIN, min(I_MAX, integral + KI * error * dt))
    u = KP * error + integral + 0.3
    u = max(0.0, min(1.0, u))
    return u, {"integral": integral, "steps": state.get("steps", 0) + 1}
