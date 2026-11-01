"""TCLab plants: the APMonitor simulator (`TCLabSim`) and the physical board (`TCLabHardware`).

TRUSTED CODE ONLY. Parameters, disturbance mechanisms and this source must never reach the agent.

Normalization (both classes): y = clamp((T1 - 15) / 60, 0, 1); input u in [0, 1] -> Q1 = 100 u %.
Independent high-temperature interlock at T1 >= 69 °C (0.90 normalized), same level as the
supervisor's hard cutoff.

How TCLabModel time works (tclab 1.0.0, investigated 2026-11-01)
----------------------------------------------------------------
* `TCLabModel(synced=True)` (default) integrates up to `labtime.time() - tstart` on every property
  access. `labtime` is a module-global wall-clock (time.time()) scaled by a rate; `tclab.setup(
  connected=False, speedup=N)` only sets that global rate, and `tclab.clock()` adapts the rate on
  the fly. Both are wall-clock driven and NOT deterministic.
* `TCLabModel(synced=False)` makes `update()` with no argument a no-op; `update(t)` Euler-integrates
  (substep `maxstep = 0.2 s`) from `tlast` to `t`. This is the deterministic path. Caveat: the
  constructor sets `tstart = tlast = labtime.time()` (a wall-clock number), so we set `tlast = 0`
  after construction and then call `update(k * dt)` ourselves.
* `.T1` / `.scan()` add noise with the GLOBAL `random.normalvariate(0, 0.043)` (unseeded, shared
  process state) then quantize to 0.3223 °C steps. We therefore read the noiseless `_T1` and apply
  our own seeded noise with the same std plus the model's own `quantize()`.
* The model is second order per heater: heater block H1 (`dH1 = P1*Q1/5720 + (Ta-H1)/20 -
  (H1-H2)/100`, P1 = 200) and a sensor that lags it, `dT1 = (H1 - T1)/140`. Ambient `Ta` (default
  21 °C) is a plain attribute read on every update, so it is settable. `_P1` is the heater power
  scale (exposed as the `P1` property) and is what we vary per seed.

`h_true` naming: `true_state()["h_true"]` is the normalized noiseless sensor temperature
(T1_true - 15) / 60, unclamped. The key name is kept from the tank so metrics need no change.
"""
from __future__ import annotations

import atexit
import contextlib
import io
import logging
import math
import time
import weakref
from collections import deque
from collections.abc import Callable
from typing import Any

import numpy as np

from backend.plant.base import PlantAdapter
from backend.schemas import DisturbanceSpec, Observation

log = logging.getLogger(__name__)

DT = 1.0
T_ZERO_C = 15.0
T_SPAN_C = 60.0
INTERLOCK_C = 69.0
MAX_DELAY_S = 300.0

PUBLIC_DESCRIPTION = (
    "A small electric heater with a temperature sensor. Input u in [0,1] is heater power; "
    "the device loses heat to the room on its own. Output y in [0,1] is a normalized "
    "temperature reading (0 = 15 °C, 1 = 75 °C)."
)

# Seed (machine) range: heater power scale applied to TCLabModel's P1 (nominal 200).
GAIN_SCALE_RANGE = (0.90, 1.10)
# Scenario (episode) ranges.
AMBIENT_RANGE_C = (18.0, 26.0)
NOISE_STD_C = 0.043  # TCLabModel's own measurement noise std
# Seeded disturbance defaults when DisturbanceSpec.magnitude is None.
DEFAULT_LAG_DELAY_S = (90.0, 150.0)  # actuator_lag: magnitude = delay in SECONDS
DEFAULT_PUMP_DERATE = (0.25, 0.40)  # heater power * (1 - m)
DEFAULT_EXTRA_LEAK = (0.40, 0.60)  # heat-loss coefficient * (1 + m) (a fan)
DEFAULT_DRAIN_SHIFT = (0.20, 0.35)  # same mechanism as extra_leak, smaller default
BASE_LOSS_PER_S = 1.0 / 20.0  # TCLabModel's heater-to-ambient coefficient
SENSOR_TAU_S = 140.0  # TCLabModel's sensor-body time constant; a fan also cools the sensor body


def normalize(temp_c: float) -> float:
    """y = clamp((T - 15) / 60, 0, 1)."""
    return _clamp((float(temp_c) - T_ZERO_C) / T_SPAN_C, 0.0, 1.0)


def _validate_u(u_applied: float) -> float:
    try:
        u = float(u_applied)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"plant input not a number: {u_applied!r}") from exc
    if not math.isfinite(u) or u < 0.0 or u > 1.0:
        raise ValueError(f"plant input out of range or non-finite: {u!r}")
    return u


def _clamp(x: float, lo: float, hi: float) -> float:
    return lo if x < lo else min(x, hi)


# =========================================================================== simulator
class TCLabSim(PlantAdapter):
    """APMonitor TCLabModel, stepped deterministically (unsynced) by exactly 1.0 s per `step()`.

    `seed` -> machine: heater power scale in GAIN_SCALE_RANGE (TCLabModel P1 = 200 * scale).
    `scenario` (default `seed`) -> episode: ambient/initial temperature Ta in 18-26 °C (the board
    starts at equilibrium with the room), the measurement-noise stream, and the seeded default
    disturbance magnitudes.

    Disturbance families (applied at t >= at_t):
      * actuator_lag : pure command delay (FIFO) of `magnitude` SECONDS (default 90-150 s; a thermal plant with tau ~150 s tolerates a 30 s delay, see IMPLEMENTATION_STATUS). The
        physical demo disturbance (foam over the sensor) is really a sensor lag; the operator
        declares it as `actuator_lag` because both make the closed-loop response slower and later.
      * pump_derate  : heater power * (1 - magnitude) (a weaker heater).
      * extra_leak   : a fan. Heater-block loss coefficient grows by (1 + magnitude) AND the sensor
        body loses heat directly to ambient at magnitude * (T1 - Ta) / 140 °C/s, so cooling at u = 0 is
        visibly faster (the observable signature that separates a fan from a weaker heater).
      * drain_shift  : identical mechanism to extra_leak with a smaller default (kept so the four
        frozen family names stay valid on every plant).
    """

    def __init__(self) -> None:
        self._model: Any = None
        self._seed: int | None = None
        self._scenario: int | None = None
        self._rng: np.random.Generator | None = None
        self._gain_scale = 1.0
        self._Ta = 21.0
        self._defaults: dict[str, float] = {}
        self._k = 0
        self._y = 0.0
        self._hist: deque[float] = deque()
        self._disturbances: list[DisturbanceSpec] = []

    @property
    def dt(self) -> float:
        return DT

    def reset(self, seed: int, scenario: int | None = None) -> Observation:
        from tclab import TCLabModel  # local import: keep module import cheap

        scenario = int(seed) if scenario is None else int(scenario)
        prng = np.random.default_rng(np.random.SeedSequence([int(seed), 20]))
        srng = np.random.default_rng(np.random.SeedSequence([scenario, 21]))
        self._rng = np.random.default_rng(np.random.SeedSequence([scenario, 22]))
        self._gain_scale = float(prng.uniform(*GAIN_SCALE_RANGE))
        self._Ta = float(srng.uniform(*AMBIENT_RANGE_C))
        self._defaults = {
            "lag_delay_s": float(srng.uniform(*DEFAULT_LAG_DELAY_S)),
            "pump_derate": float(srng.uniform(*DEFAULT_PUMP_DERATE)),
            "extra_leak": float(srng.uniform(*DEFAULT_EXTRA_LEAK)),
            "drain_shift": float(srng.uniform(*DEFAULT_DRAIN_SHIFT)),
        }
        with contextlib.redirect_stdout(io.StringIO()):  # TCLabModel prints banners
            m = TCLabModel(synced=False)
        m.tstart = 0.0
        m.tlast = 0.0
        m.Ta = self._Ta
        m._P1 = 200.0 * self._gain_scale
        m._T1 = m._T2 = m._H1 = m._H2 = self._Ta
        m._Q1 = m._Q2 = 0.0
        self._model = m
        self._seed, self._scenario = int(seed), scenario
        self._k = 0
        n = int(MAX_DELAY_S / DT) + 3
        self._hist = deque([0.0] * n, maxlen=n)
        self._disturbances = []
        self._y = self._measure()
        return self.observe()

    def observe(self) -> Observation:
        self._require_reset()
        return Observation(t=self._t, y=self._y, interlock_high=bool(self._model._T1 >= INTERLOCK_C))

    def step(self, u_applied: float) -> Observation:
        self._require_reset()
        u = _validate_u(u_applied)
        m = self._model
        t0 = self._t
        gain, extra_loss, delay_s = self._effective(t0)
        self._hist.append(u)
        n = min(round(delay_s / DT), len(self._hist) - 1)
        u_seen = self._hist[-1 - n]
        m._Q1 = _clamp(100.0 * u_seen * gain, 0.0, 100.0)  # direct set: Q1() would call update()
        # integrate in TCLabModel's own 0.2 s substeps, applying the extra (fan) loss operator-split
        sub = m.maxstep
        nsub = max(1, round(DT / sub))
        for j in range(1, nsub + 1):
            ts = t0 + DT * j / nsub
            m.update(ts)
            if extra_loss > 0.0:
                # A fan cools the whole assembly: the heater block (its TCLabModel loss coefficient grows by
                # (1 + extra_loss)) AND the sensor body directly, so the observable cooling at u = 0 is faster.
                # Without the second term a fan is indistinguishable from a weaker heater in the readings.
                m._H1 -= (DT / nsub) * extra_loss * BASE_LOSS_PER_S * (m._H1 - m.Ta)
                m._T1 -= (DT / nsub) * extra_loss * (m._T1 - m.Ta) / SENSOR_TAU_S
        self._k += 1
        self._y = self._measure()
        return self.observe()

    def true_state(self) -> dict:
        """TRUSTED ONLY. `h_true` = (T1_true - 15) / 60 (noiseless sensor temperature, unclamped)."""
        self._require_reset()
        return {"h_true": (float(self._model._T1) - T_ZERO_C) / T_SPAN_C, "t": self._t}

    def public_description(self) -> str:
        return PUBLIC_DESCRIPTION

    def schedule_disturbance(self, spec: DisturbanceSpec) -> None:
        self._require_reset()
        self._disturbances.append(spec)

    def emergency_stop(self) -> None:
        if self._model is not None:
            self._model._Q1 = 0.0
            self._model._Q2 = 0.0
        for i in range(len(self._hist)):
            self._hist[i] = 0.0

    def hidden_params(self) -> dict:
        """TRUSTED ONLY (audit logs)."""
        self._require_reset()
        return {
            "kind": "tclab_model",
            "seed": self._seed,
            "scenario": self._scenario,
            "gain_scale": self._gain_scale,
            "P1": 200.0 * self._gain_scale,
            "Ta_c": self._Ta,
            "noise_std_c": NOISE_STD_C,
            "disturbance_defaults": dict(self._defaults),
            "disturbances": [
                {"family": d.family, "at_t": d.at_t, "applied": {"magnitude": self._magnitude(d)}}
                for d in self._disturbances
            ],
        }

    # internals
    @property
    def _t(self) -> float:
        return float(self._k) * DT

    def _require_reset(self) -> None:
        if self._model is None:
            raise RuntimeError("TCLabSim.reset(seed) must be called first")

    def _measure(self) -> float:
        assert self._rng is not None
        reading = self._model.quantize(self._model._T1 + float(self._rng.normal(0.0, NOISE_STD_C)))
        return normalize(reading)

    def _magnitude(self, d: DisturbanceSpec) -> float:
        if d.magnitude is not None:
            return float(d.magnitude)
        return self._defaults["lag_delay_s" if d.family == "actuator_lag" else d.family]

    def _effective(self, t: float) -> tuple[float, float, float]:
        gain, extra_loss, delay = 1.0, 0.0, 0.0
        for d in self._disturbances:
            if t + 1e-9 < d.at_t:
                continue
            mag = self._magnitude(d)
            if d.family == "pump_derate":
                gain *= max(0.0, 1.0 - mag)
            elif d.family in ("extra_leak", "drain_shift"):
                extra_loss += max(0.0, mag)
            elif d.family == "actuator_lag":
                delay = max(delay, min(max(0.0, mag), MAX_DELAY_S))
        return gain, extra_loss, delay


# =========================================================================== hardware
_LIVE_BOARDS: weakref.WeakSet[TCLabHardware] = weakref.WeakSet()


@atexit.register
def _heaters_off_at_exit() -> None:  # pragma: no cover - process teardown
    for hw in list(_LIVE_BOARDS):
        with contextlib.suppress(Exception):
            hw._heaters_off()


class TCLabHardware(PlantAdapter):
    """The physical TCLab board over USB serial, real time, dt = 1.0 s.

    No hidden truth exists on hardware: `true_state()` returns the latest READING (normalized,
    unclamped) and the interlock uses the reading. Scoring of physical runs happens on a
    ThermalTwin fitted to the board's discovery experiments, not on this class.

    `lab_factory`, `clock` and `sleep` are injectable for tests (default: `tclab.TCLab(port=port)`,
    `time.monotonic`, `time.sleep`). The board is opened lazily on first `reset()`, so importing
    or constructing this class never touches serial.
    """

    COOL_BELOW_C = 35.0
    COOL_TIMEOUT_S = 120.0

    def __init__(
        self,
        port: str = "",
        lab_factory: Callable[[], Any] | None = None,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.port = port
        self._lab_factory = lab_factory
        self._clock = clock
        self._sleep = sleep
        self._lab: Any = None
        self._k = 0
        self._T1 = math.nan
        self._next_tick: float | None = None
        self.overruns = 0
        _LIVE_BOARDS.add(self)

    @property
    def dt(self) -> float:
        return DT

    def _open(self) -> Any:
        if self._lab is None:
            if self._lab_factory is not None:
                self._lab = self._lab_factory()
            else:
                from tclab import TCLab  # lazy: needs pyserial and a board

                self._lab = TCLab(port=self.port)
        return self._lab

    def reset(self, seed: int, scenario: int | None = None) -> Observation:
        """Heaters off, wait until T1 < 35 °C or 120 s, then t = 0. `seed`/`scenario` are ignored:
        there is one physical machine and the room sets the initial conditions."""
        lab = self._open()
        self._heaters_off()
        start = self._clock()
        while True:
            T = float(lab.T1)
            waited = self._clock() - start
            if T < self.COOL_BELOW_C:
                log.info("TCLab reset: T1=%.2f °C below %.0f °C after %.0f s", T, self.COOL_BELOW_C, waited)
                break
            if waited >= self.COOL_TIMEOUT_S:
                log.warning("TCLab reset: cool-down timeout after %.0f s, T1=%.2f °C", waited, T)
                break
            self._sleep(1.0)
        self._k = 0
        self._next_tick = None
        self._T1 = T
        return self.observe()

    def observe(self) -> Observation:
        if self._lab is None:
            raise RuntimeError("TCLabHardware.reset() must be called first")
        self._T1 = float(self._lab.T1)
        return self._obs()

    def _obs(self) -> Observation:
        return Observation(t=self._t, y=normalize(self._T1), interlock_high=bool(self._T1 >= INTERLOCK_C))

    def step(self, u_applied: float) -> Observation:
        if self._lab is None:
            raise RuntimeError("TCLabHardware.reset() must be called first")
        u = _validate_u(u_applied)
        self._lab.Q1(100.0 * u)
        self._wait_for_tick()
        self._k += 1
        return self.observe()

    def _wait_for_tick(self) -> None:
        """Sleep to the next point of a fixed monotonic schedule (no cumulative drift). If we are
        more than one period late, count an overrun and re-anchor the schedule to now."""
        now = self._clock()
        if self._next_tick is None:
            self._next_tick = now + DT
        delay = self._next_tick - now
        if delay > 0:
            self._sleep(delay)
            self._next_tick += DT
        elif -delay > DT:
            self.overruns += 1
            log.warning("TCLab tick overrun by %.3f s; re-anchoring schedule", -delay)
            self._next_tick = now + DT
        else:
            self._next_tick += DT

    def true_state(self) -> dict:
        """No hidden truth on hardware: the latest reading, normalized and unclamped."""
        return {"h_true": (self._T1 - T_ZERO_C) / T_SPAN_C, "t": self._t}

    def public_description(self) -> str:
        return PUBLIC_DESCRIPTION

    def schedule_disturbance(self, spec: DisturbanceSpec) -> None:
        raise NotImplementedError(
            "TCLabHardware: physical disturbances (fan, foam, weaker supply) are applied by the "
            f"operator by hand; declare {spec.family!r} at t={spec.at_t} in the run log instead."
        )

    def emergency_stop(self) -> None:
        self._heaters_off()

    def close(self) -> None:
        if self._lab is None:
            return
        self._heaters_off()
        with contextlib.suppress(Exception):
            self._lab.close()
        self._lab = None
        _LIVE_BOARDS.discard(self)

    def _heaters_off(self) -> None:
        if self._lab is not None:
            self._lab.Q1(0)
            self._lab.Q2(0)

    @property
    def _t(self) -> float:
        return float(self._k) * DT
