"""Transparent baselines for scoring only. NEVER shown to the model (project rule: baselines exist for scoring only)."""
from __future__ import annotations

import math

# Detuned PI used as the EXISTENCE PROOF that the actuator_lag disturbance is repairable
# (tests/test_baselines.py). Found by a small manual sweep on DISTURBANCE_SEEDS (kp in {0.6, 0.7, 0.8,
# 1.0}, ki in {0.02, 0.03, 0.04}); kp=0.8/ki=0.03 was the most robust. It is a scoring reference only
# and is NEVER shown to the model.
SLOW_PID_TUNING = {"kp": 0.8, "ki": 0.03, "kd": 0.0}


class PIDController:
    """Textbook PID: derivative on measurement, conditional integration + integral clamp.

    u = u_bias + kp*e + ki*I - kd*dy/dt, clamped to [0, 1]; e = target - y.
    Anti-windup: the integral only accumulates when the output is not saturated in the direction
    the error pushes, and u_bias + ki*I is clamped to [0, 1] (with u_bias = 0 this is the original
    clamp of ki*I to [0, 1], so the frozen baselines are unchanged).
    ``u_bias`` (default 0.0) is the classical "manual reset" output offset used by the relay auto-tuned
    baselines (evaluation/autotune.py); it is not used by the frozen fixed/slow PID baselines.
    Default tuning (kp=3.0, ki=0.15, kd=0.0) is the brief's starting point and holds band on
    exploration seeds 1-10 (see tests/test_baselines.py); it was NOT tuned on held-out seeds.
    It is deliberately aggressive: it rejects every offset disturbance but loses its stability
    margin under the actuator_lag (dynamics) disturbance. See SLOW_PID_TUNING for a tuning that
    survives it.
    """

    isolation = "trusted"

    def __init__(self, kp: float = 3.0, ki: float = 0.15, kd: float = 0.0, name: str = "baseline_pid",
                 u_bias: float = 0.0):
        self.kp, self.ki, self.kd, self.name = float(kp), float(ki), float(kd), name
        self.u_bias = float(u_bias)
        self.reset()

    def reset(self) -> None:
        self._i = 0.0
        self._y_prev: float | None = None

    def step(self, obs: dict) -> float:
        y, target, dt = float(obs["y"]), float(obs["target"]), float(obs["dt"])
        if not (math.isfinite(y) and math.isfinite(target) and math.isfinite(dt)) or dt <= 0:
            return 0.0
        e = target - y
        d = 0.0 if self._y_prev is None else (y - self._y_prev) / dt
        self._y_prev = y
        i_new = self._i + e * dt
        if self.ki > 0:
            lo = -self.u_bias / self.ki if self.u_bias else 0.0  # exactly the original clamp when u_bias == 0
            i_new = min(max(i_new, lo), (1.0 - self.u_bias) / self.ki)
        u_unsat = self.u_bias + self.kp * e + self.ki * i_new - self.kd * d
        saturating = (u_unsat > 1.0 and e > 0) or (u_unsat < 0.0 and e < 0)
        if not saturating:
            self._i = i_new
        u = self.u_bias + self.kp * e + self.ki * self._i - self.kd * d
        return min(max(u, 0.0), 1.0)

    def close(self) -> None:
        pass


class OnOffController:
    """Bang-bang with hysteresis: full pump below target-h, off above target+h, else hold."""

    isolation = "trusted"

    def __init__(self, hysteresis: float = 0.02, name: str = "baseline_onoff"):
        self.hysteresis, self.name = float(hysteresis), name
        self.reset()

    def reset(self) -> None:
        self._u = 0.0

    def step(self, obs: dict) -> float:
        y, target = float(obs["y"]), float(obs["target"])
        if not math.isfinite(y):
            return 0.0
        if y < target - self.hysteresis:
            self._u = 1.0
        elif y > target + self.hysteresis:
            self._u = 0.0
        return self._u

    def close(self) -> None:
        pass


class ConstantController:
    """Always requests the same command (tests / exploration helpers)."""

    isolation = "trusted"

    def __init__(self, u: float, name: str = "constant"):
        self.u, self.name = float(u), name

    def reset(self) -> None:
        pass

    def step(self, obs: dict) -> float:
        return self.u

    def close(self) -> None:
        pass
