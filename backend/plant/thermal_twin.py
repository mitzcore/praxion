"""ThermalTwin: first-order-plus-dead-time (FOPDT) heater model, fitted from discovery experiments.

TRUSTED CODE ONLY. This is the evaluator's stand-in for a PHYSICAL run: the real TCLab board cannot
be reset to a hidden scenario or replayed on frozen seeds, so candidate controllers are scored on a
twin fitted to the constant-input experiments the agent ran on the real board.

Model (temperatures in °C, u = heater fraction in [0, 1]):

    dT/dt = ( K * g * u(t - L - L_extra) - (1 + m) * (T - Ta) ) / tau
    y     = clamp( (T + N(0, noise_std) - 15) / 60, 0, 1 )

  * K       steady-state rise above ambient at full power (°C)
  * tau     time constant (s)
  * L       pure input delay (s), fractional delays are linearly interpolated
  * Ta      ambient temperature (°C)
  * g, m, L_extra are disturbance terms (1, 0, 0 when undisturbed)

The state is integrated exactly (zero-order hold on u) with dt = 1.0 s, internally in normalized
units x = (T - 15) / 60, so K_n = K / 60 and Ta_n = (Ta - 15) / 60.

Disturbance families (same names and default ranges as TCLabSim, applied at t >= at_t):
  * actuator_lag : extra pure delay of `magnitude` seconds (default seeded 90-150 s)
  * pump_derate  : heater gain multiplied by (1 - magnitude) (default 0.25-0.40)
  * extra_leak   : heat-loss coefficient multiplied by (1 + magnitude) (default 0.40-0.60)
  * drain_shift  : same mechanism as extra_leak, smaller default (0.20-0.35)

`fit_twin` FAILURE MODES (each is reported in `FitReport.warnings`, never silently):
  * experiments much shorter than tau: K and tau are only weakly identified separately (their
    ratio K/tau, the initial slope, is well identified). Extrapolation to steady state is then
    unreliable; `tau_at_bound` / `short_relative_to_tau` warnings are raised.
  * no input excitation (all experiments at the same u, or all at u = 0): K is unidentifiable.
  * a segment that starts while the plant is still responding to an UNRECORDED earlier input:
    the model assumes u = `u_before` (default 0) before the first recorded tick of each segment.
  * clamped readings (y == 0 below 15 °C, y == 1 above 75 °C) carry no information and are masked;
    if the room is below 15 °C the early part of every cold-start experiment is masked.
  * the real TCLab is second order (heater block + sensor lag); FOPDT folds the faster mode into L.
"""
from __future__ import annotations

import math
from collections import deque
from collections.abc import Callable, Sequence

import numpy as np
from pydantic import BaseModel, Field
from scipy.optimize import least_squares, minimize_scalar
from scipy.signal import lfilter

from backend.plant.base import PlantAdapter
from backend.schemas import DisturbanceSpec, Observation, Trace

DT = 1.0
T_ZERO_C = 15.0  # y = 0
T_SPAN_C = 60.0  # y = 1 at 75 °C
INTERLOCK_C = 69.0  # 0.90 normalized; same independent high-temperature switch as TCLabSim
MAX_DELAY_S = 300.0

DEFAULT_LAG_DELAY_S = (90.0, 150.0)
DEFAULT_PUMP_DERATE = (0.25, 0.40)
DEFAULT_EXTRA_LEAK = (0.40, 0.60)
DEFAULT_DRAIN_SHIFT = (0.20, 0.35)

L_GRID_S = tuple(float(x) for x in range(0, 61, 5))  # coarse dead-time grid 0..60 s
TAU_BOUNDS_S = (2.0, 3000.0)
K_BOUNDS_C = (0.0, 300.0)


def to_norm(temp_c: float) -> float:
    return (temp_c - T_ZERO_C) / T_SPAN_C


def to_celsius(x: float) -> float:
    return x * T_SPAN_C + T_ZERO_C


class FitReport(BaseModel):
    """TRUSTED ONLY. Quality of a twin fit, in normalized units (1.0 = 60 °C)."""

    rmse: float
    per_trace_rmse: list[float]
    n_points: int
    n_masked: int
    n_segments: int
    grid_L_s: list[float]
    grid_rmse: list[float]
    warnings: list[str] = Field(default_factory=list)


class TwinParams(BaseModel):
    """TRUSTED ONLY. FOPDT parameters in physical units."""

    K_c: float  # steady-state rise at full power, °C
    tau_s: float
    L_s: float
    Ta_c: float
    noise_std_c: float = 0.05
    ambient_jitter_c: float = 0.0  # optional per-scenario +/- variation of Ta (0 = one fixed room)
    report: FitReport | None = None


# --------------------------------------------------------------------------- simulation core
def _delayed(u: np.ndarray, delay_steps: float, u_before: float) -> np.ndarray:
    """u_d[k] = u(k - delay) with linear interpolation for fractional delay, u_before before t=0."""
    n = math.floor(delay_steps)
    f = delay_steps - n
    pad = np.full(n + 1, u_before, dtype=float)
    ext = np.concatenate([pad, u])
    # ext index of u[k] is k + n + 1; u[k-n] -> k + 1; u[k-n-1] -> k
    k = np.arange(u.size)
    return (1.0 - f) * ext[k + 1] + f * ext[k]


def simulate_fopdt(
    u: np.ndarray, K_n: float, tau: float, L: float, Ta_n: float, x0: float, dt: float = DT, u_before: float = 0.0
) -> np.ndarray:
    """Noiseless normalized state x_k at each tick, given u_k applied over [t_k, t_k + dt]."""
    u = np.asarray(u, dtype=float)
    if u.size == 0:
        return np.zeros(0)
    a = math.exp(-dt / tau)
    ud = _delayed(u, L / dt, u_before)
    w = lfilter([(1.0 - a) * K_n], [1.0, -a], ud)
    z = np.concatenate([[0.0], w[:-1]]) + (x0 - Ta_n) * a ** np.arange(u.size)
    return Ta_n + z


# --------------------------------------------------------------------------- plant
class ThermalTwin(PlantAdapter):
    """FOPDT heater plant with the same API, normalization and disturbance families as TCLabSim.

    `seed` does not change the machine (the twin IS one fitted machine). `scenario` (default `seed`)
    selects the measurement-noise stream, the seeded default disturbance magnitudes and, if
    `params.ambient_jitter_c > 0`, an ambient offset in [-jitter, +jitter] °C. The episode starts at
    thermal equilibrium with the room.
    """

    def __init__(self, params: TwinParams) -> None:
        self.params = params
        self._seed: int | None = None
        self._scenario: int | None = None
        self._rng: np.random.Generator | None = None
        self._defaults: dict[str, float] = {}
        self._Ta_c = params.Ta_c
        self._x = 0.0
        self._y = 0.0
        self._k = 0
        self._hist: deque[float] = deque()
        self._disturbances: list[DisturbanceSpec] = []

    @classmethod
    def from_params(cls, params: TwinParams) -> ThermalTwin:
        return cls(params)

    @property
    def dt(self) -> float:
        return DT

    def reset(self, seed: int, scenario: int | None = None) -> Observation:
        scenario = int(seed) if scenario is None else int(scenario)
        srng = np.random.default_rng(np.random.SeedSequence([scenario, 11]))
        self._rng = np.random.default_rng(np.random.SeedSequence([scenario, 12]))
        jitter = float(srng.uniform(-1.0, 1.0)) * self.params.ambient_jitter_c
        self._defaults = {
            "lag_delay_s": float(srng.uniform(*DEFAULT_LAG_DELAY_S)),
            "pump_derate": float(srng.uniform(*DEFAULT_PUMP_DERATE)),
            "extra_leak": float(srng.uniform(*DEFAULT_EXTRA_LEAK)),
            "drain_shift": float(srng.uniform(*DEFAULT_DRAIN_SHIFT)),
        }
        self._seed, self._scenario = int(seed), scenario
        self._Ta_c = self.params.Ta_c + jitter
        self._x = to_norm(self._Ta_c)
        self._k = 0
        n = math.ceil((self.params.L_s + MAX_DELAY_S) / DT) + 3
        self._hist = deque([0.0] * n, maxlen=n)
        self._disturbances = []
        self._y = self._measure()
        return self.observe()

    def observe(self) -> Observation:
        self._require_reset()
        return Observation(t=self._t, y=self._y, interlock_high=bool(to_celsius(self._x) >= INTERLOCK_C))

    def step(self, u_applied: float) -> Observation:
        self._require_reset()
        u = _validate_u(u_applied)
        p = self.params
        gain, loss, extra_delay = self._effective(self._t)
        self._hist.append(u)
        d = min((p.L_s + extra_delay) / DT, len(self._hist) - 2)
        n = math.floor(d)
        f = d - n
        u_d = (1.0 - f) * self._hist[-1 - n] + f * self._hist[-2 - n]
        tau_eff = p.tau_s / loss
        a = math.exp(-DT / tau_eff)
        Ta_n = to_norm(self._Ta_c)
        x_ss = Ta_n + (p.K_c / T_SPAN_C) * gain * u_d / loss
        self._x = x_ss + (self._x - x_ss) * a
        self._k += 1
        self._y = self._measure()
        return self.observe()

    def true_state(self) -> dict:
        """TRUSTED ONLY. `h_true` (name kept for metrics compatibility) is the noiseless normalized
        temperature (T - 15) / 60, NOT clamped."""
        self._require_reset()
        return {"h_true": float(self._x), "t": self._t}

    def public_description(self) -> str:
        return (
            "A small electric heater with a temperature sensor. Input u in [0,1] is heater power; "
            "the device loses heat to the room on its own. Output y in [0,1] is a normalized "
            "temperature reading (0 = 15 °C, 1 = 75 °C)."
        )

    def schedule_disturbance(self, spec: DisturbanceSpec) -> None:
        self._require_reset()
        self._disturbances.append(spec)

    def emergency_stop(self) -> None:
        for i in range(len(self._hist)):
            self._hist[i] = 0.0

    def hidden_params(self) -> dict:
        """TRUSTED ONLY (audit logs)."""
        self._require_reset()
        return {
            "kind": "thermal_twin_fopdt",
            "seed": self._seed,
            "scenario": self._scenario,
            "K_c": self.params.K_c, "tau_s": self.params.tau_s, "L_s": self.params.L_s,
            "Ta_c": self._Ta_c, "noise_std_c": self.params.noise_std_c,
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
        if self._rng is None:
            raise RuntimeError("ThermalTwin.reset(seed) must be called first")

    def _measure(self) -> float:
        assert self._rng is not None
        noise = float(self._rng.normal(0.0, self.params.noise_std_c)) / T_SPAN_C
        return _clamp(self._x + noise, 0.0, 1.0)

    def _magnitude(self, d: DisturbanceSpec) -> float:
        if d.magnitude is not None:
            return float(d.magnitude)
        return self._defaults["lag_delay_s" if d.family == "actuator_lag" else d.family]

    def _effective(self, t: float) -> tuple[float, float, float]:
        gain, loss, extra_delay = 1.0, 1.0, 0.0
        for d in self._disturbances:
            if t + 1e-9 < d.at_t:
                continue
            m = self._magnitude(d)
            if d.family == "pump_derate":
                gain *= max(0.0, 1.0 - m)
            elif d.family in ("extra_leak", "drain_shift"):
                loss *= 1.0 + max(0.0, m)
            elif d.family == "actuator_lag":
                extra_delay = max(extra_delay, min(max(0.0, m), MAX_DELAY_S))
        return gain, loss, extra_delay


def twin_factory(params: TwinParams) -> Callable[[], ThermalTwin]:
    """Plant factory for the evaluator: a fresh twin per episode."""
    frozen = params.model_copy(deep=True)
    return lambda: ThermalTwin.from_params(frozen)


# --------------------------------------------------------------------------- fitting
def _segments(traces: Sequence[Trace], dt: float) -> list[list[int]]:
    """Group consecutive traces that continue in time (no reset between them) into one segment."""
    segs: list[list[int]] = []
    last_t: float | None = None
    for i, tr in enumerate(traces):
        if not tr.steps:
            continue
        t0 = tr.steps[0].t
        if segs and last_t is not None and abs(t0 - (last_t + dt)) < 1e-6 * max(1.0, dt):
            segs[-1].append(i)
        else:
            segs.append([i])
        last_t = tr.steps[-1].t
    return segs


def fit_twin(traces: list[Trace], dt: float = DT, u_before: float = 0.0) -> TwinParams:
    """Least-squares FOPDT fit of K, tau, L, Ta from constant-input experiment traces.

    Traces that follow each other in time (next trace starts one tick after the previous ended) are
    simulated as one continuous segment; each segment gets its own free initial state, and the
    input before a segment's first tick is assumed to be `u_before`. L is searched on a coarse grid
    (0..60 s, 5 s) with K, tau, Ta and initial states fitted by `scipy.optimize.least_squares` at
    each grid point, then refined by bounded scalar minimisation around the best grid point.
    Raises ValueError only if there is no usable data; weak fits return with warnings.
    """
    segs = _segments(traces, dt)
    data: list[tuple[np.ndarray, np.ndarray, np.ndarray, list[tuple[int, int, int]]]] = []
    n_masked = 0
    for seg in segs:
        ys, us, slices = [], [], []
        off = 0
        for i in seg:
            y = traces[i].y()
            u = traces[i].u_applied()
            ys.append(y)
            us.append(u)
            slices.append((i, off, off + y.size))
            off += y.size
        y = np.concatenate(ys)
        u = np.nan_to_num(np.concatenate(us), nan=0.0)
        mask = (y > 0.0) & (y < 1.0) & np.isfinite(y)
        n_masked += int((~mask).sum())
        data.append((y, u, mask, slices))
    n_points = int(sum(int(m.sum()) for _, _, m, _ in data))
    if n_points < 3:
        raise ValueError(f"fit_twin: not enough unclamped data points ({n_points})")
    warnings: list[str] = []
    all_u = np.concatenate([d[1] for d in data])
    if float(np.ptp(all_u)) < 0.05 and float(np.max(all_u)) < 0.05:
        warnings.append("no_excitation: all inputs ~0; K is unidentifiable")
    elif float(np.ptp(all_u)) < 0.05 and len(segs) <= 1:
        warnings.append("single_input_level: K and Ta are only separable through the transient")

    nseg = len(data)
    first_y = [float(y[m][0]) if m.any() else 0.0 for y, _, m, _ in data]
    ta0 = float(min(first_y))
    # initial guesses: theta = [K_n, log(tau), Ta_n, x0_1..x0_n]
    theta0 = np.array([0.8, math.log(150.0), ta0, *first_y])
    lo = np.array([K_BOUNDS_C[0] / T_SPAN_C, math.log(TAU_BOUNDS_S[0]), -1.0, *([-1.0] * nseg)])
    hi = np.array([K_BOUNDS_C[1] / T_SPAN_C, math.log(TAU_BOUNDS_S[1]), 1.5, *([2.0] * nseg)])

    def residuals(theta: np.ndarray, L: float) -> np.ndarray:
        K_n, tau, Ta_n = theta[0], math.exp(theta[1]), theta[2]
        out = []
        for j, (y, u, m, _) in enumerate(data):
            x = simulate_fopdt(u, K_n, tau, L, Ta_n, theta[3 + j], dt, u_before)
            out.append((x - y)[m])
        return np.concatenate(out)

    def inner(L: float, start: np.ndarray) -> tuple[float, np.ndarray]:
        r = least_squares(residuals, np.clip(start, lo + 1e-9, hi - 1e-9), bounds=(lo, hi), args=(L,),
                          x_scale="jac", max_nfev=400)
        return float(np.sqrt(np.mean(r.fun**2))), r.x

    grid_rmse: list[float] = []
    best = (math.inf, theta0, 0.0)
    for L in L_GRID_S:
        rm, th = inner(L, best[1] if math.isfinite(best[0]) else theta0)
        rm2, th2 = inner(L, theta0)  # also from the neutral start; keep the better one
        if rm2 < rm:
            rm, th = rm2, th2
        grid_rmse.append(rm)
        if rm < best[0]:
            best = (rm, th, L)
    step = L_GRID_S[1] - L_GRID_S[0]
    a, b = max(0.0, best[2] - step), min(L_GRID_S[-1] + step, best[2] + step)
    cache: dict[float, tuple[float, np.ndarray]] = {}

    def obj(L: float) -> float:
        cache[L] = inner(L, best[1])
        return cache[L][0]

    res = minimize_scalar(obj, bounds=(a, b), method="bounded", options={"xatol": 0.1})
    L_best, (_rm_best, th_best) = best[2], (best[0], best[1])
    if res.success and float(res.x) in cache and cache[float(res.x)][0] <= best[0]:
        L_best = float(res.x)
        _rm_best, th_best = cache[L_best]

    K_n, tau, Ta_n = float(th_best[0]), math.exp(float(th_best[1])), float(th_best[2])
    # per-trace rmse with the final params
    per_trace = [math.nan] * len(traces)
    resid_all = []
    for j, (y, u, m, slices) in enumerate(data):
        x = simulate_fopdt(u, K_n, tau, L_best, Ta_n, float(th_best[3 + j]), dt, u_before)
        r = x - y
        resid_all.append(r[m])
        for i, s0, s1 in slices:
            mm = m[s0:s1]
            per_trace[i] = float(np.sqrt(np.mean(r[s0:s1][mm] ** 2))) if mm.any() else math.nan
    resid = np.concatenate(resid_all)
    if tau >= TAU_BOUNDS_S[1] * 0.99 or tau <= TAU_BOUNDS_S[0] * 1.01:
        warnings.append(f"tau_at_bound: tau={tau:.1f}s")
    if K_n * T_SPAN_C >= K_BOUNDS_C[1] * 0.99:
        warnings.append("K_at_bound")
    longest = max(float(y.size) * dt for y, _, _, _ in data)
    if longest < 1.0 * tau:
        warnings.append(f"short_relative_to_tau: longest segment {longest:.0f}s < tau {tau:.0f}s; K extrapolated")
    if L_best >= L_GRID_S[-1]:
        warnings.append("L_at_grid_edge: dead time may exceed 60 s")
    report = FitReport(
        rmse=float(np.sqrt(np.mean(resid**2))), per_trace_rmse=per_trace, n_points=n_points, n_masked=n_masked,
        n_segments=nseg, grid_L_s=list(L_GRID_S), grid_rmse=grid_rmse, warnings=warnings,
    )
    return TwinParams(
        K_c=K_n * T_SPAN_C, tau_s=tau, L_s=L_best, Ta_c=to_celsius(Ta_n),
        noise_std_c=max(1e-3, float(np.std(resid)) * T_SPAN_C), report=report,
    )


# --------------------------------------------------------------------------- helpers
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
