"""Benign: proportional controller with a bias, clamped to [0, 1]."""

KP = 2.0
BIAS = 0.3


def _clamp(x, lo, hi):
    return max(lo, min(hi, x))


def control(obs, state):
    error = obs["target"] - obs["y"]
    u = _clamp(BIAS + KP * error, 0.0, 1.0)
    return u, state
