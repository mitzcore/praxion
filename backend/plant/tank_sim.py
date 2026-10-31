"""TankSimulator: seeded water-reservoir plant with hidden dynamics (plan section 5.1).

TRUSTED CODE ONLY. Nothing in this module (parameters, ranges, disturbance mechanisms,
source) may be shown to the agent.

Dynamics per step (dt = 0.1 s):
    u_del  = u_cmd delayed by (delay_nominal + delay_extra(t)) seconds (FIFO transport delay)
    u_act += (dt/tau_eff(t)) * (u_del - u_act), clamp 0..1        # tau_eff = tau * lag_factor(t)
    q_in   = pump_gain * eff(t) * max(0, u_act - deadband) / max(1e-6, 1 - deadband)
    q_out  = leak_base + leak_extra(t) + drain_coeff(t) * sqrt(max(h, 0))
    h     += dt * (q_in - q_out) / tank_area, clamp 0..1
    y      = clamp(h + N(0, noise_std), 0, 1)

Parameter ranges are chosen so that, for EVERY seed (enforced by tests/test_plant_boundary.py):
  * steady state at u=1 exceeds 0.9 (overflow is genuinely possible; safety matters),
  * steady state at u=0 is 0,
  * the linearised open-loop time constant near h=0.6 is within 15-45 s,
  * pump_gain / tank_area <= MAX_RATE_AT_FULL_DUTY (0.10/s) so the supervisor's
    worst-case envelope (safety/envelope.py) is actually conservative,
  * the target 0.60 stays reachable (steady state at u=1 >= 0.65) after the worst default
    disturbance of each family, so a self-repair gate is physically achievable.
History: the original plan ranges violated several of these; pump_gain min was raised from the
requested 0.060 to 0.064 and drain_coeff min from 0.040 to 0.042 (see status doc).

Disturbance families:
  * offset families (pump_derate, extra_leak, drain_shift) change the steady-state operating
    point; integral feedback rejects them.
  * dynamics family (actuator_lag) multiplies tau by a seeded factor and inserts an extra
    transport delay; this breaks the stability margin of an aggressively tuned loop.
"""
from __future__ import annotations

import math
from collections import deque

import numpy as np

from backend.plant.base import PlantAdapter
from backend.schemas import DisturbanceSpec, Observation

DT = 0.1
# Independent high-level interlock: an IDEAL float switch on the true level (no noise, no delay),
# separate from the analog level sensor. Same level as the supervisor's hard cutoff.
INTERLOCK_LEVEL = 0.90

# (low, high) uniform sampling ranges. TRUSTED ONLY. Draw order is fixed (_PARAM_ORDER).
PARAM_RANGES: dict[str, tuple[float, float]] = {
    "tank_area": (0.90, 1.20),
    "pump_gain": (0.064, 0.090),
    "deadband": (0.05, 0.20),
    "tau": (1.0, 4.0),
    "drain_coeff": (0.042, 0.050),
    "leak_base": (0.000, 0.003),
    "noise_std": (0.003, 0.010),
    "delay_nominal": (0.3, 1.0),  # always-on transport delay (s)
}
DELAY_NOMINAL_RANGE = PARAM_RANGES["delay_nominal"]
# Episode-specific (scenario) ranges. Drawn from the SCENARIO stream, not the plant seed.
SCENARIO_RANGES: dict[str, tuple[float, float]] = {
    "h0": (0.15, 0.45),
}
# Seeded defaults for disturbances when magnitude is None.
DEFAULT_PUMP_DERATE = (0.20, 0.30)
DEFAULT_DRAIN_SHIFT = (0.30, 0.50)
# extra_leak default is sized so the steady state at the duty that holds this nominal level drops
# by a seeded amount in this range (>= 0.15 required). Frozen so every controller faces the same
# disturbance on the same seed regardless of its behaviour.
EXTRA_LEAK_REF_LEVEL = 0.60
DEFAULT_EXTRA_LEAK_DROP = (0.18, 0.25)
# actuator_lag: tau multiplied by a factor in this range, plus this much extra transport delay (s).
# `DisturbanceSpec.magnitude`, if given, overrides the tau factor only.
DEFAULT_LAG_TAU_FACTOR = (1.0, 1.5)
DEFAULT_LAG_DELAY_S = (18.0, 22.0)

_PARAM_ORDER = ("tank_area", "pump_gain", "deadband", "tau", "drain_coeff", "leak_base", "noise_std", "delay_nominal")


class TankSimulator(PlantAdapter):
    """Seeded tank plant. Deterministic given seed and input sequence."""

    def __init__(self) -> None:
        self._seed: int | None = None
        self._scenario: int | None = None
        self._p: dict[str, float] = {}
        self._defaults: dict[str, float] = {}
        self._noise_rng: np.random.Generator | None = None
        self._k = 0
        self._h = 0.0
        self._u_cmd = 0.0
        self._u_act = 0.0
        self._y = 0.0
        self._hist: deque[float] = deque()
        self._disturbances: list[DisturbanceSpec] = []

    # ------------------------------------------------------------------ interface
    @property
    def dt(self) -> float:
        return DT

    def reset(self, seed: int, scenario: int | None = None) -> Observation:
        """Reset deterministically. Clears scheduled disturbances.

        `seed` selects the MACHINE: the hidden physical parameters (PARAM_RANGES).
        `scenario` (default: `seed`) selects the EPISODE: initial level, the noise stream and the
        seeded default disturbance magnitudes. Same (seed, scenario) -> identical traces.
        """
        scenario = int(seed) if scenario is None else int(scenario)
        # Three independent streams; the integer tag keeps them disjoint even when seed == scenario.
        prng = np.random.default_rng(np.random.SeedSequence([int(seed), 0]))
        srng = np.random.default_rng(np.random.SeedSequence([scenario, 1]))
        self._noise_rng = np.random.default_rng(np.random.SeedSequence([scenario, 2]))

        self._p = {k: float(prng.uniform(*PARAM_RANGES[k])) for k in _PARAM_ORDER}
        # Scenario draws in a fixed order so the stream never depends on which disturbance runs.
        # New draws are only ever APPENDED so existing scenarios keep their earlier values.
        self._p["h0"] = float(srng.uniform(*SCENARIO_RANGES["h0"]))
        self._defaults = {
            "pump_derate": float(srng.uniform(*DEFAULT_PUMP_DERATE)),
            "drain_shift": float(srng.uniform(*DEFAULT_DRAIN_SHIFT)),
            "extra_leak_drop": float(srng.uniform(*DEFAULT_EXTRA_LEAK_DROP)),
            "lag_tau_factor": float(srng.uniform(*DEFAULT_LAG_TAU_FACTOR)),
            "lag_delay_s": float(srng.uniform(*DEFAULT_LAG_DELAY_S)),
        }
        self._seed = int(seed)
        self._scenario = scenario
        self._k = 0
        self._h = self._p["h0"]
        self._u_cmd = 0.0
        self._u_act = 0.0
        max_delay = self._p["delay_nominal"] + DEFAULT_LAG_DELAY_S[1] + 1.0
        self._hist = deque([0.0] * (round(max_delay / DT) + 2), maxlen=round(max_delay / DT) + 2)
        self._disturbances = []
        self._y = self._measure()
        return self.observe()

    def observe(self) -> Observation:
        """Latest noisy level `y` plus the independent binary interlock (true level >= INTERLOCK_LEVEL)."""
        self._require_reset()
        return Observation(t=self._t, y=self._y, interlock_high=bool(self._h >= INTERLOCK_LEVEL))

    def step(self, u_applied: float) -> Observation:
        self._require_reset()
        try:
            u = float(u_applied)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"plant input not a number: {u_applied!r}") from exc
        if not math.isfinite(u) or u < 0.0 or u > 1.0:
            raise ValueError(f"plant input out of range or non-finite: {u!r}")
        p = self._p
        dt = DT
        eff, leak_extra, drain, tau_factor, delay_extra = self._effective(self._t)

        self._u_cmd = u
        self._hist.append(u)  # newest at the right; history defaults to 0 before t=0
        n_delay = round((p["delay_nominal"] + delay_extra) / dt)
        n_delay = min(n_delay, len(self._hist) - 1)
        u_del = self._hist[-1 - n_delay]
        tau = p["tau"] * tau_factor
        self._u_act = _clamp(self._u_act + (dt / tau) * (u_del - self._u_act), 0.0, 1.0)
        db = p["deadband"]
        q_in = p["pump_gain"] * eff * max(0.0, self._u_act - db) / max(1e-6, 1.0 - db)
        q_out = p["leak_base"] + leak_extra + drain * math.sqrt(max(self._h, 0.0))
        self._h = _clamp(self._h + dt * (q_in - q_out) / p["tank_area"], 0.0, 1.0)
        self._k += 1
        self._y = self._measure()
        return self.observe()

    def true_state(self) -> dict:
        """TRUSTED ONLY: true level and time. Must never reach the agent view."""
        self._require_reset()
        return {"h_true": float(self._h), "t": self._t}

    def public_description(self) -> str:
        return (
            "A water reservoir. Input u in [0,1] is pump duty and raises the level; "
            "the reservoir drains on its own. Output y in [0,1] is a noisy level reading."
        )

    def schedule_disturbance(self, spec: DisturbanceSpec) -> None:
        self._require_reset()
        self._disturbances.append(spec)

    def emergency_stop(self) -> None:
        """Actuator to 0 immediately, and flush the delay line so no queued command is applied."""
        self._u_cmd = 0.0
        self._u_act = 0.0
        for i in range(len(self._hist)):
            self._hist[i] = 0.0

    # ------------------------------------------------------------------ trusted audit
    def hidden_params(self) -> dict:
        """TRUSTED ONLY (evaluator audit logs). Never used by anything agent-facing."""
        self._require_reset()
        return {
            "seed": self._seed,
            "scenario": self._scenario,
            **self._p,
            "disturbance_defaults": dict(self._defaults),
            "disturbances": [
                {"family": d.family, "at_t": d.at_t, "applied": self._applied(d)} for d in self._disturbances
            ],
        }

    # ------------------------------------------------------------------ internals
    @property
    def _t(self) -> float:
        return round(self._k * DT, 10)

    def _require_reset(self) -> None:
        if self._noise_rng is None:
            raise RuntimeError("TankSimulator.reset(seed) must be called first")

    def _measure(self) -> float:
        assert self._noise_rng is not None
        return _clamp(self._h + float(self._noise_rng.normal(0.0, self._p["noise_std"])), 0.0, 1.0)

    def _magnitude(self, d: DisturbanceSpec) -> float:
        if d.magnitude is not None:
            return float(d.magnitude)
        if d.family == "pump_derate":
            return self._defaults["pump_derate"]
        if d.family == "drain_shift":
            return self._defaults["drain_shift"]
        if d.family == "actuator_lag":
            return self._defaults["lag_tau_factor"]
        # extra_leak: q_in that holds EXTRA_LEAK_REF_LEVEL is leak + c*sqrt(h_ref); an extra leak L
        # moves the steady state to (sqrt(h_ref) - L/c)^2. Pick L for the seeded drop.
        c = self._p["drain_coeff"]
        h_ref = EXTRA_LEAK_REF_LEVEL
        h_new = max(0.0, h_ref - self._defaults["extra_leak_drop"])
        return c * (math.sqrt(h_ref) - math.sqrt(h_new))

    def _applied(self, d: DisturbanceSpec) -> dict:
        if d.family == "actuator_lag":
            return {"tau_factor": max(1.0, self._magnitude(d)), "delay_s": self._defaults["lag_delay_s"]}
        return {"magnitude": self._magnitude(d)}

    def _effective(self, t: float) -> tuple[float, float, float, float, float]:
        eff, leak_extra, drain = 1.0, 0.0, self._p["drain_coeff"]
        tau_factor, delay_extra = 1.0, 0.0
        for d in self._disturbances:
            if t + 1e-9 < d.at_t:
                continue
            m = self._magnitude(d)
            if d.family == "pump_derate":
                eff *= max(0.0, 1.0 - m)
            elif d.family == "extra_leak":
                leak_extra += max(0.0, m)
            elif d.family == "drain_shift":
                drain *= 1.0 + m
            elif d.family == "actuator_lag":
                tau_factor *= max(1.0, m)
                delay_extra = max(delay_extra, self._defaults["lag_delay_s"])
        return eff, leak_extra, drain, tau_factor, delay_extra


def _clamp(x: float, lo: float, hi: float) -> float:
    return lo if x < lo else min(x, hi)
