import math
def _clamp(v, lo, hi):
    if not math.isfinite(v):
        return lo
    if v < lo:
        return lo
    if v > hi:
        return hi
    return float(v)

def control(obs, state):
    try:
        y_raw = obs.get("y", 0.5)
    except Exception:
        y_raw = 0.5
    try:
        tgt_raw = obs.get("target", 0.5)
    except Exception:
        tgt_raw = 0.5
    try:
        dt_raw = obs.get("dt", 1.0)
    except Exception:
        dt_raw = 1.0
    try:
        y = float(y_raw)
    except Exception:
        y = 0.5
    try:
        target = float(tgt_raw)
    except Exception:
        target = 0.5
    try:
        dt = float(dt_raw)
    except Exception:
        dt = 1.0
    if not math.isfinite(y):
        y = 0.5
    if not math.isfinite(target):
        target = 0.5
    if not math.isfinite(dt) or dt <= 0.0:
        dt = 1.0
    if dt < 0.2:
        dt = 0.2
    if dt > 5.0:
        dt = 5.0
    y = _clamp(y, 0.0, 1.0)
    target = _clamp(target, 0.0, 1.0)
    yf_prev = None
    integ_prev = 0.0
    try:
        if isinstance(state, dict):
            v = state.get("yf", None)
            if v is not None:
                v = float(v)
                if math.isfinite(v):
                    yf_prev = _clamp(v, 0.0, 1.0)
            w = state.get("i", 0.0)
            w = float(w)
            if math.isfinite(w):
                integ_prev = _clamp(w, -0.3, 0.3)
    except Exception:
        yf_prev = None
        integ_prev = 0.0
    if yf_prev is None:
        yf_prev = y
    tau_f = 6.0
    alpha = dt / (tau_f + dt)
    if alpha < 0.0:
        alpha = 0.0
    if alpha > 1.0:
        alpha = 1.0
    yf = yf_prev + alpha * (y - yf_prev)
    if not math.isfinite(yf):
        yf = y
    yf = _clamp(yf, 0.0, 1.0)
    ambient = 0.05
    gain = 1.014
    ff = (target - ambient) / gain
    ff = _clamp(ff, 0.0, 1.0)
    Kp = 1.5
    Ki = 0.012
    e = target - yf
    if not math.isfinite(e):
        e = 0.0
    integ = integ_prev
    enable = abs(e) < 0.15
    u_now_unsat = ff + Kp * e + integ
    saturated_high = u_now_unsat > 1.0 and e > 0.0
    saturated_low = u_now_unsat < 0.0 and e < 0.0
    if enable and (not saturated_high) and (not saturated_low):
        integ = integ + Ki * e * dt
        integ = _clamp(integ, -0.25, 0.25)
    else:
        integ = _clamp(integ, -0.25, 0.25)
    if yf > 0.75:
        if integ > 0.0:
            integ = 0.0
    u = ff + Kp * e + integ
    if yf >= 0.85:
        u = 0.0
    u = _clamp(u, 0.0, 1.0)
    new_state = {"yf": float(yf), "i": float(integ)}
    return (float(u), new_state)
