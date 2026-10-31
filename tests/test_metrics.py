from __future__ import annotations

import json
import math

import pytest

from backend.evaluation.metrics import compute_metrics, post_disturbance_mae
from backend.schemas import Trace, TraceStep


def _step(t, h, u=0.5, ureq=None, override=False, reason="ok"):
    return TraceStep(t=t, y=h + 0.001, h_true=h, u_requested=u if ureq is None else ureq, u_applied=u,
                     override=override, reason=reason)


def test_hand_computed_metrics():
    # dt = 1.0, target 0.6, scored from t=2
    steps = [
        _step(0.0, 0.20, u=1.0),
        _step(1.0, 0.95, u=0.0, ureq=math.nan, override=True, reason="controller_exception:ZeroDivisionError"),
        _step(2.0, 0.60, u=0.5),
        _step(3.0, 0.70, u=0.5, ureq=1.5, override=True, reason="clamped"),
        _step(4.0, 0.56, u=0.2),
    ]
    tr = Trace(steps=steps, dt=1.0, target=0.6)
    m = compute_metrics(tr, scored_from_s=2.0)
    assert m.mae == pytest.approx((0.0 + 0.1 + 0.04) / 3)
    assert m.in_band_fraction == pytest.approx(2 / 3)
    assert m.actuation_energy == pytest.approx(1.0 + 0 + 0.25 + 0.25 + 0.04)
    assert m.override_count == 2
    assert m.hard_violations == 1
    assert m.invalid_outputs == 2  # exception + out-of-range request
    assert m.adaptation_latency_s is None
    assert m.steps == 5 and m.scored_steps == 3


def _dist_trace():
    # dt 1.0, disturbance at t=3; final in-band run t=5..14 (10 steps, to the end) -> latency 2.0
    hs = [0.6, 0.6, 0.6, 0.4, 0.5] + [0.6] * 10
    steps = [_step(float(i), h) for i, h in enumerate(hs)]
    return Trace(steps=steps, dt=1.0, target=0.6, disturbance_at=3.0)


def test_adaptation_latency():
    m = compute_metrics(_dist_trace(), scored_from_s=0.0)
    assert m.adaptation_latency_s == pytest.approx(2.0)


def test_adaptation_latency_zero_when_never_leaving_band():
    hs = [0.6, 0.6, 0.6] + [0.6] * 12
    tr = Trace(steps=[_step(float(i), h) for i, h in enumerate(hs)], dt=1.0, target=0.6, disturbance_at=3.0)
    assert compute_metrics(tr, 0.0).adaptation_latency_s == 0.0


def test_adaptation_latency_none_when_limit_cycling_at_end():
    hs = [0.6, 0.6, 0.6] + [0.6] * 10 + [0.4, 0.6, 0.8]
    tr = Trace(steps=[_step(float(i), h) for i, h in enumerate(hs)], dt=1.0, target=0.6, disturbance_at=3.0)
    assert compute_metrics(tr, 0.0).adaptation_latency_s is None


def test_adaptation_latency_never():
    hs = [0.6, 0.6, 0.4] + [0.6] * 5 + [0.4] + [0.6] * 5
    tr = Trace(steps=[_step(float(i), h) for i, h in enumerate(hs)], dt=1.0, target=0.6, disturbance_at=2.0)
    assert compute_metrics(tr, 0.0).adaptation_latency_s is None


def test_post_disturbance_mae():
    tr = _dist_trace()
    hs = [0.4, 0.5] + [0.6] * 10
    assert post_disturbance_mae(tr) == pytest.approx(sum(abs(h - 0.6) for h in hs) / len(hs))
    with pytest.raises(ValueError):
        post_disturbance_mae(Trace(steps=tr.steps, dt=1.0, target=0.6))


def test_agent_safe_projection():
    steps = [_step(i * 0.1, 0.5 + 0.0001 * i, ureq=math.nan if i == 7 else 0.5) for i in range(1200)]
    tr = Trace(steps=steps, dt=0.1, target=0.6, disturbance_at=60.0, meta={"seed": 1003, "secret": "x"})
    pts = tr.agent_safe()
    assert 0 < len(pts) <= 60
    for p in pts:
        assert set(p) == {"t", "y", "target", "u_requested", "u_applied", "override"}
    blob = json.dumps(pts)  # JSON-serialisable (NaN -> null)
    assert "h_true" not in blob and "1003" not in blob and "secret" not in blob and "reason" not in blob
    assert pts[0]["t"] == 0.0
    small = Trace(steps=steps[:10], dt=0.1, target=0.6).agent_safe()
    assert len(small) == 10
    assert Trace(steps=[], dt=0.1, target=0.6).agent_safe() == []


def test_trace_array_helpers():
    tr = _dist_trace()
    assert tr.times().shape == tr.y().shape == tr.h_true().shape == tr.u_applied().shape == (15,)
