import math
def _clamp(v, lo, hi):
    if not math.isfinite(v):
        return lo
    if v < lo:
        return lo
    if v > hi:
        return hi
    return v
def _ff_for_target(t):
    if not math.isfinite(t):
        t = 0.6
    if t < 0.0:
        t = 0.0
    if t > 1.0:
        t = 1.0
    ff = 0.57 + (t - 0.6) * 1.5
    if ff < 0.05:
        ff = 0.05
    if ff > 0.85:
        ff = 0.85
    return ff
def control(obs, state):
    try:
        y_raw = obs.get("y", 0.6)
        tgt_raw = obs.get("target", 0.6)
        dt_raw = obs.get("dt", 0.2)
    except Exception:
        return (0.0, {"yf": 0.6, "i": 0.0})
    try:
        y = float(y_raw)
    except Exception:
        y = 0.6
    try:
        target = float(tgt_raw)
    except Exception:
        target = 0.6
    try:
        dt = float(dt_raw)
    except Exception:
        dt = 0.2
    if not math.isfinite(y):
        y = target
    if not math.isfinite(target):
        target = 0.6
    if not math.isfinite(dt) or dt <= 0.0:
        dt = 0.2
    if dt < 0.02:
        dt = 0.02
    if dt > 1.0:
        dt = 1.0
    if y < -0.1:
        y = -0.1
    if y > 1.1:
        y = 1.1
    if target < 0.0:
        target = 0.0
    if target > 1.0:
        target = 1.0
    if not isinstance(state, dict):
        state = {}
    yf_prev = state.get("yf", None)
    i_prev = state.get("i", 0.0)
    try:
        yf_prev = float(yf_prev) if yf_prev is not None else y
    except Exception:
        yf_prev = y
    try:
        i_prev = float(i_prev)
    except Exception:
        i_prev = 0.0
    if not math.isfinite(yf_prev):
        yf_prev = y
    if not math.isfinite(i_prev):
        i_prev = 0.0
    if yf_prev < 0.0:
        yf_prev = 0.0
    if yf_prev > 1.0:
        yf_prev = 1.0
    if i_prev < -0.3:
        i_prev = -0.3
    if i_prev > 0.3:
        i_prev = 0.3
    tau_f = 0.8
    alpha = dt / (tau_f + dt)
    if alpha < 0.02:
        alpha = 0.02
    if alpha > 1.0:
        alpha = 1.0
    yf = alpha * y + (1.0 - alpha) * yf_prev
    yf = _clamp(yf, 0.0, 1.0)
    e = target - yf
    ff = _ff_for_target(target)
    Kp = 1.0
    Ki = 0.20
    p = Kp * e
    u_pre = ff + p + i_prev
    allow_int = True
    if abs(e) > 0.25:
        allow_int = False
    if u_pre >= 0.85 and e > 0.0:
        allow_int = False
    if u_pre <= 0.0 and e < 0.0:
        allow_int = False
    if allow_int:
        i_new = i_prev + Ki * e * dt
    else:
        i_new = i_prev * 0.999
    i_new = _clamp(i_new, -0.20, 0.25)
    u = ff + p + i_new
    if yf >= 0.80:
        u = 0.0
    elif yf > 0.70:
        if u > 0.25:
            u = 0.25
    u = _clamp(u, 0.0, 1.0)
    if not math.isfinite(u):
        u = 0.0
        i_new = 0.0
    return (float(u), {"yf": float(yf), "i": float(i_new)})
