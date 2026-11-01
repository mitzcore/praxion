import math
def _clamp(v, lo, hi):
    if not math.isfinite(v):
        return lo
    if v < lo:
        return lo
    if v > hi:
        return hi
    return v
def control(obs, state):
    if not isinstance(state, dict):
        state = {}
    try:
        y_m = float(obs.get("y", 0.5))
    except:
        y_m = 0.5
    try:
        tgt = float(obs.get("target", 0.5))
    except:
        tgt = 0.5
    try:
        dt = float(obs.get("dt", 1.0))
    except:
        dt = 1.0
    if not math.isfinite(y_m):
        y_m = 0.5
    if not math.isfinite(tgt):
        tgt = 0.5
    if not math.isfinite(dt) or dt <= 0.0:
        dt = 1.0
    if dt < 0.1:
        dt = 0.1
    if dt > 10.0:
        dt = 10.0
    if y_m < 0.0:
        y_m = 0.0
    if y_m > 1.0:
        y_m = 1.0
    if tgt < 0.0:
        tgt = 0.0
    if tgt > 1.0:
        tgt = 1.0
    yf_prev = state.get("yf", y_m)
    integ_prev = state.get("integ", 0.0)
    try:
        yf_prev = float(yf_prev)
    except:
        yf_prev = y_m
    try:
        integ_prev = float(integ_prev)
    except:
        integ_prev = 0.0
    if not math.isfinite(yf_prev):
        yf_prev = y_m
    if not math.isfinite(integ_prev):
        integ_prev = 0.0
    yf_prev = _clamp(yf_prev, 0.0, 1.0)
    integ_prev = _clamp(integ_prev, -0.35, 0.35)
    Tf = 10.0
    alpha = dt / (Tf + dt)
    if alpha < 0.0:
        alpha = 0.0
    if alpha > 1.0:
        alpha = 1.0
    yf = yf_prev + alpha * (y_m - yf_prev)
    if not math.isfinite(yf):
        yf = yf_prev
    yf = _clamp(yf, 0.0, 1.0)
    Y_AMB = 0.08
    K = 1.10
    Kp = 1.4
    Ki = 0.008
    U_MIN = 0.0
    U_MAX = 0.70
    INT_LIM = 0.30
    E_FREEZE = 0.12
    ff = (tgt - Y_AMB) / K
    if not math.isfinite(ff):
        ff = 0.382
    if ff < 0.0:
        ff = 0.0
    if ff > 0.65:
        ff = 0.65
    e = tgt - yf
    if not math.isfinite(e):
        e = 0.0
    integ = integ_prev
    if abs(e) < E_FREEZE:
        integ = integ_prev + Ki * e * dt
        integ = _clamp(integ, -INT_LIM, INT_LIM)
    u_raw = ff + Kp * e + integ
    if not math.isfinite(u_raw):
        u_raw = ff
        integ = integ_prev
    u = u_raw
    if u < U_MIN:
        u = U_MIN
    if u > U_MAX:
        u = U_MAX
    saturated_high = u_raw > U_MAX
    saturated_low = u_raw < U_MIN
    if (saturated_high and e > 0.0) or (saturated_low and e < 0.0):
        integ = integ_prev
        u_raw2 = ff + Kp * e + integ
        if not math.isfinite(u_raw2):
            u_raw2 = ff
        u = u_raw2
        if u < U_MIN:
            u = U_MIN
        if u > U_MAX:
            u = U_MAX
    if not math.isfinite(u):
        u = ff
    if u < 0.0:
        u = 0.0
    if u > 1.0:
        u = 1.0
    return (float(u), {"yf": float(yf), "integ": float(integ)})
