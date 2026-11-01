import math
def _clamp(v, lo, hi):
    if v < lo:
        return lo
    if v > hi:
        return hi
    return v
def control(obs, state):
    y_m = 0.5
    tgt = 0.5
    dt = 1.0
    try:
        y_m = float(obs["y"])
    except Exception:
        y_m = 0.5
    try:
        tgt = float(obs["target"])
    except Exception:
        tgt = 0.5
    try:
        dt = float(obs["dt"])
    except Exception:
        dt = 1.0
    if not math.isfinite(y_m):
        y_m = 0.5
    if not math.isfinite(tgt):
        tgt = 0.5
    if not math.isfinite(dt) or dt <= 0.0:
        dt = 1.0
    if dt < 0.05:
        dt = 0.05
    if dt > 5.0:
        dt = 5.0
    if y_m < 0.0:
        y_m = 0.0
    if y_m > 1.0:
        y_m = 1.0
    if tgt < 0.0:
        tgt = 0.0
    if tgt > 1.0:
        tgt = 1.0
    if state is None:
        state = {}
    yf = state.get("yf", None)
    integ = state.get("integ", 0.0)
    try:
        yf = float(yf)
    except Exception:
        yf = y_m
    try:
        integ = float(integ)
    except Exception:
        integ = 0.0
    if not math.isfinite(yf):
        yf = y_m
    if not math.isfinite(integ):
        integ = 0.0
    yf = _clamp(yf, 0.0, 1.0)
    integ = _clamp(integ, -0.35, 0.35)
    Tf = 8.0
    Kp = 2.2
    Ki = 0.014
    Kest = 0.885
    yamb = 0.05
    alpha = dt / (Tf + dt)
    yf = yf + alpha * (y_m - yf)
    e = tgt - yf
    uff = (tgt - yamb) / Kest
    uff = _clamp(uff, 0.0, 1.0)
    prop = Kp * e
    u_test = uff + prop + integ
    blocked_high = (u_test >= 1.0) and (e > 0.0)
    blocked_low = (u_test <= 0.0) and (e < 0.0)
    if not (blocked_high or blocked_low):
        integ = integ + Ki * e * dt
        integ = _clamp(integ, -0.35, 0.35)
    u = uff + prop + integ
    u = _clamp(u, 0.0, 1.0)
    if yf > 0.85:
        u = 0.0
    elif yf > 0.80:
        if u > 0.20:
            u = 0.20
    if not math.isfinite(u):
        u = _clamp(uff, 0.0, 1.0)
    state["yf"] = float(yf)
    state["integ"] = float(integ)
    return float(u), state
