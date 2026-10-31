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
    yf = state.get("yf", None)
    integ = state.get("integ", 0.0)
    try:
        integ = float(integ)
    except Exception:
        integ = 0.0
    if not math.isfinite(integ):
        integ = 0.0
    try:
        yf_f = float(yf) if yf is not None else None
    except Exception:
        yf_f = None
    if yf_f is None or not math.isfinite(yf_f):
        yf_f = y_m
    else:
        yf_f = _clamp(yf_f, 0.0, 1.0)
        tau = 0.8
        alpha = dt / (tau + dt)
        max_step = 0.32 * dt + 0.06
        diff = y_m - yf_f
        if diff > max_step:
            yf_f = yf_f + alpha * max_step
        elif diff < -max_step:
            yf_f = yf_f - alpha * max_step
        else:
            yf_f = yf_f + alpha * diff
    e = tgt - yf_f
    FF = 0.50
    KP = 2.0
    KI = 0.25
    I_MAX = 0.35
    E_GATE = 0.10
    integ = _clamp(integ, -I_MAX, I_MAX)
    p_term = KP * e
    u_test = FF + p_term + KI * integ
    can_int = True
    if abs(e) > E_GATE:
        can_int = False
    elif u_test >= 1.0 and e > 0.0:
        can_int = False
    elif u_test <= 0.0 and e < 0.0:
        can_int = False
    if can_int:
        integ = integ + e * dt
        integ = _clamp(integ, -I_MAX, I_MAX)
    u = FF + p_term + KI * integ
    if yf_f >= 0.78:
        u = 0.0
    elif yf_f >= 0.74:
        if u > 0.15:
            u = 0.15
    u = _clamp(u, 0.0, 1.0)
    if not math.isfinite(u):
        u = FF
        integ = 0.0
    new_state = {"yf": float(yf_f), "integ": float(integ)}
    return (float(u), new_state)
