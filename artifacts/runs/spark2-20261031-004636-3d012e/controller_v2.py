import math
def _clamp(v, lo, hi):
    if v < lo:
        return lo
    if v > hi:
        return hi
    return v
def control(obs, state):
    try:
        y_m = float(obs.get("y", 0.6))
    except Exception:
        y_m = 0.6
    try:
        tgt = float(obs.get("target", 0.6))
    except Exception:
        tgt = 0.6
    try:
        dt_in = float(obs.get("dt", 0.1))
    except Exception:
        dt_in = 0.1
    if not math.isfinite(y_m):
        y_m = 0.6
    if not math.isfinite(tgt):
        tgt = 0.6
    tgt = _clamp(tgt, 0.0, 1.0)
    y_m = _clamp(y_m, 0.0, 1.0)
    if not math.isfinite(dt_in) or dt_in <= 0.0:
        dt = 0.1
    else:
        dt = _clamp(dt_in, 0.02, 1.0)
    if not isinstance(state, dict):
        state = {}
    try:
        yf = float(state.get("yf", y_m))
    except Exception:
        yf = y_m
    try:
        rate = float(state.get("rate", 0.0))
    except Exception:
        rate = 0.0
    try:
        ff = float(state.get("ff", 0.52))
    except Exception:
        ff = 0.52
    try:
        integ = float(state.get("integ", 0.0))
    except Exception:
        integ = 0.0
    if not math.isfinite(yf):
        yf = y_m
    if not math.isfinite(rate):
        rate = 0.0
    if not math.isfinite(ff):
        ff = 0.52
    if not math.isfinite(integ):
        integ = 0.0
    yf = _clamp(yf, 0.0, 1.0)
    rate = _clamp(rate, -0.2, 0.2)
    ff = _clamp(ff, 0.15, 0.85)
    integ = _clamp(integ, -0.35, 0.35)
    first = ("yf" not in state)
    if first:
        yf = y_m
        rate = 0.0
    else:
        tau_f = 1.0
        alpha = dt / (tau_f + dt)
        yf_new = yf + alpha * (y_m - yf)
        yf_new = _clamp(yf_new, 0.0, 1.0)
        raw = (yf_new - yf) / dt
        raw = _clamp(raw, -0.25, 0.25)
        tau_r = 1.2
        beta = dt / (tau_r + dt)
        rate = rate + beta * (raw - rate)
        rate = _clamp(rate, -0.2, 0.2)
        yf = yf_new
    e = tgt - yf
    if abs(e) < 0.12 and abs(rate) < 0.03 and yf < 0.72 and yf > 0.15:
        ff = ff + e * dt * 0.04
        ff = _clamp(ff, 0.15, 0.85)
    KP = 1.3
    KI = 0.18
    KD = 2.5
    I_MAX = 0.35
    p_term = KP * e
    d_term = KD * rate
    u_test = ff + p_term + KI * integ - d_term
    can_int = True
    if abs(e) > 0.12:
        can_int = False
    elif abs(rate) > 0.02:
        can_int = False
    elif u_test >= 1.0 and e > 0.0:
        can_int = False
    elif u_test <= 0.0 and e < 0.0:
        can_int = False
    if can_int:
        integ = integ + e * dt
        integ = _clamp(integ, -I_MAX, I_MAX)
    u = ff + p_term + KI * integ - d_term
    y_guard = yf
    tmp = y_m - 0.01
    if tmp > y_guard:
        y_guard = tmp
    if y_guard >= 0.80 or y_m >= 0.84:
        u = 0.0
    elif y_guard >= 0.75:
        if u > 0.05:
            u = 0.05
    elif y_guard >= 0.70:
        if u > 0.20:
            u = 0.20
    elif y_guard >= 0.65 and rate > 0.015:
        if u > 0.30:
            u = 0.30
    y_pred = yf + rate * 4.0
    if y_pred > 0.80:
        if u > 0.10:
            u = 0.10
    elif y_pred > 0.74:
        if u > 0.30:
            u = 0.30
    elif y_pred > 0.70 and rate > 0.01:
        if u > 0.40:
            u = 0.40
    u = _clamp(u, 0.0, 1.0)
    if not math.isfinite(u):
        u = _clamp(ff, 0.0, 1.0)
        integ = 0.0
    new_state = {"yf": float(yf), "rate": float(rate), "ff": float(ff), "integ": float(integ)}
    return (float(u), new_state)
