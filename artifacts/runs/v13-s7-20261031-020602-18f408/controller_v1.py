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
    if not isinstance(state, dict):
        state = {}
    try:
        y_raw = obs.get("y", 0.6)
    except Exception:
        y_raw = 0.6
    try:
        t_raw = obs.get("target", 0.6)
    except Exception:
        t_raw = 0.6
    try:
        dt_raw = obs.get("dt", 0.2)
    except Exception:
        dt_raw = 0.2
    try:
        dt = float(dt_raw)
    except Exception:
        dt = 0.2
    if not math.isfinite(dt) or dt <= 0.0:
        dt = 0.2
    if dt < 0.02:
        dt = 0.02
    if dt > 1.0:
        dt = 1.0
    try:
        target = float(t_raw)
    except Exception:
        target = 0.6
    if not math.isfinite(target):
        target = 0.6
    if target < 0.0:
        target = 0.0
    if target > 0.85:
        target = 0.85
    try:
        y = float(y_raw)
    except Exception:
        y = float("nan")
    try:
        yf_prev = float(state.get("yf", float("nan")))
    except Exception:
        yf_prev = float("nan")
    if not math.isfinite(y):
        if math.isfinite(yf_prev):
            y = yf_prev
        else:
            y = target
    if y < 0.0:
        y = 0.0
    if y > 1.0:
        y = 1.0
    if not math.isfinite(yf_prev):
        yf = y
    else:
        if yf_prev < 0.0:
            yf_prev = 0.0
        if yf_prev > 1.0:
            yf_prev = 1.0
        tau_f = 1.5
        alpha = dt / (tau_f + dt)
        yf = yf_prev + alpha * (y - yf_prev)
        if not math.isfinite(yf):
            yf = yf_prev
        if yf < 0.0:
            yf = 0.0
        if yf > 1.0:
            yf = 1.0
    try:
        integ_prev = float(state.get("integ", 0.0))
    except Exception:
        integ_prev = 0.0
    if not math.isfinite(integ_prev):
        integ_prev = 0.0
    if integ_prev < -0.35:
        integ_prev = -0.35
    if integ_prev > 0.35:
        integ_prev = 0.35
    Kp = 0.55
    Ki = 0.10
    I_MAX = 0.25
    FF_DZ = 0.297
    FF_K = 2.72
    U_MIN = 0.0
    U_MAX = 0.85
    ff = FF_DZ + target / FF_K
    if not math.isfinite(ff):
        ff = 0.52
    if ff < 0.15:
        ff = 0.15
    if ff > 0.75:
        ff = 0.75
    e = target - yf
    if e < -1.0:
        e = -1.0
    if e > 1.0:
        e = 1.0
    P = Kp * e
    integ = integ_prev
    if abs(e) < 0.20:
        integ = integ_prev + Ki * e * dt
        if integ < -I_MAX:
            integ = -I_MAX
        if integ > I_MAX:
            integ = I_MAX
    u_test = ff + P + integ
    if u_test > U_MAX and e > 0.0:
        integ = integ_prev
    if u_test < U_MIN and e < 0.0:
        integ = integ_prev
    u = ff + P + integ
    if yf > 0.80:
        u = 0.0
        if integ > -0.05:
            integ = -0.05
    elif yf > 0.75:
        if u > 0.25:
            u = 0.25
        if integ > 0.0:
            integ = 0.0
    u = _clamp(u, U_MIN, 1.0)
    if not math.isfinite(u):
        u = ff
        u = _clamp(u, U_MIN, 1.0)
    new_state = {"yf": float(yf), "integ": float(integ)}
    return (float(u), new_state)
