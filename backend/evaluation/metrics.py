"""Episode metrics from simulator truth (plan section 5.4). TRUSTED: uses h_true."""
from __future__ import annotations

import math

import numpy as np

from backend.evaluation.config import BAND, IN_BAND_SUSTAIN_S
from backend.schemas import Metrics, Trace

HARD_CUTOFF = 0.90


def _in_band(h: np.ndarray) -> np.ndarray:
    return (h >= BAND[0]) & (h <= BAND[1])


def _is_invalid(u_req: float, reason: str) -> bool:
    u = float(u_req)
    return reason.startswith("controller_exception") or not math.isfinite(u) or u < 0.0 or u > 1.0


def adaptation_latency(trace: Trace) -> float | None:
    """Settling time after a disturbance: seconds from disturbance_at to the start of the FINAL
    in-band run of h_true, which must last at least IN_BAND_SUSTAIN_S and extend to the end of
    the episode. 0.0 if the level never leaves the band after the disturbance. None if no
    disturbance, if the level is out of band at the end, or if the final in-band run is shorter
    than IN_BAND_SUSTAIN_S.

    Definition changed 2026-10-31 (before any official scoring): the earlier "first sustained
    in-band run" returned 0 s for controllers that were briefly in band right after the change and
    then fell into a limit cycle.
    """
    if trace.disturbance_at is None:
        return None
    t, h = trace.times(), trace.h_true()
    mask = t >= trace.disturbance_at - 1e-9
    t, ok = t[mask], _in_band(h[mask])
    if t.size == 0 or not ok[-1]:
        return None
    # walk back from the end to the start of the final in-band run
    i = ok.size - 1
    while i > 0 and ok[i - 1]:
        i -= 1
    need = max(1, round(IN_BAND_SUSTAIN_S / trace.dt))
    if ok.size - i < need:
        return None
    return float(t[i] - trace.disturbance_at)


def compute_metrics(trace: Trace, scored_from_s: float) -> Metrics:
    """Score a trace.

    mae / in_band_fraction use h_true over t >= scored_from_s. Safety and cost accounting
    (actuation_energy, override_count, hard_violations, invalid_outputs) cover the WHOLE episode:
    a violation during settling still counts. invalid_outputs counts controller exceptions and
    non-finite or out-of-[0,1] requests.
    """
    t, h, u = trace.times(), trace.h_true(), trace.u_applied()
    mask = t >= scored_from_s - 1e-9
    hs = h[mask]
    mae = float(np.mean(np.abs(hs - trace.target))) if hs.size else math.nan
    in_band = float(np.mean(_in_band(hs))) if hs.size else math.nan
    return Metrics(
        mae=mae,
        in_band_fraction=in_band,
        actuation_energy=float(np.sum(u**2) * trace.dt),
        override_count=int(sum(1 for s in trace.steps if s.override)),
        hard_violations=int(np.sum(h >= HARD_CUTOFF)),
        invalid_outputs=int(sum(1 for s in trace.steps if _is_invalid(s.u_requested, s.reason))),
        adaptation_latency_s=adaptation_latency(trace),
        steps=len(trace.steps),
        scored_steps=int(hs.size),
    )


def post_disturbance_mae(trace: Trace) -> float:
    """MAE of h_true vs target over t >= disturbance_at. Raises if the trace has no disturbance."""
    if trace.disturbance_at is None:
        raise ValueError("trace has no disturbance")
    t, h = trace.times(), trace.h_true()
    hs = h[t >= trace.disturbance_at - 1e-9]
    return float(np.mean(np.abs(hs - trace.target))) if hs.size else math.nan
