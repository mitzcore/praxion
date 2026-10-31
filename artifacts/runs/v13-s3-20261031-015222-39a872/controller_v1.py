import math
def _clamp(x, lo, hi):
    if x < lo:
        return lo
    if x > hi:
        return hi
    return x
def control(obs, state):
    KP = 0.9
    KI = 0.14
    TAU_F = 1.5
    I_LIM = 2.0
    FF0 = 0.64
    T0 = 0.6
    INV_GAIN = 0.8
    try:
        y_raw = float(obs.get("y", 0.6))
    except Exception:
        y_raw = 0.6
    try:
        target = float(obs.get("target", 0.6))
    except Exception:
        target = 0.6
    try:
        dt = float(obs.get("dt", 0.2))
    except Exception:
        dt = 0.2
    if not math.isfinite(y_raw):
        y_raw = None
    if not math.isfinite(target):
        target = 0.6
    if not math.isfinite(dt) or dt <= 0.0:
        dt = 0.2
    if dt < 0.02:
        dt = 0.02
    if dt > 1.0:
        dt = 1.0
    target = _clamp(target, 0.0, 1.0)
    try:
        yf_prev = float(state.get("yf", y_raw if y_raw is not None else target))
    except Exception:
        yf_prev = target
    try:
        I_prev = float(state.get("I", 0.0))
    except Exception:
        I_prev = 0.0
    if not math.isfinite(yf_prev):
        yf_prev = target
    if not math.isfinite(I_prev):
        I_prev = 0.0
    I_prev = _clamp(I_prev, -I_LIM, I_LIM)
    yf_prev = _clamp(yf_prev, 0.0, 1.0)
    if y_raw is None:
        y_meas = yf_prev
    else:
        y_meas = _clamp(y_raw, 0.0, 1.0)
    alpha = dt / (TAU_F + dt)
    yf = yf_prev + alpha * (y_meas - yf_prev)
    if not math.isfinite(yf):
        yf = yf_prev
    yf = _clamp(yf, 0.0, 1.0)
    e = target - yf
    ff = FF0 + INV_GAIN * (target - T0)
    ff = _clamp(ff, 0.0, 0.85)
    p = KP * e
    I_try = I_prev + e * dt
    I_try = _clamp(I_try, -I_LIM, I_LIM)
    u_try = ff + p + KI * I_try
    if (u_try > 1.0 and e > 0.0) or (u_try < 0.0 and e < 0.0):
        I_new = I_prev
        u_raw = ff + p + KI * I_new
    else:
        I_new = I_try
        u_raw = u_try
    if not math.isfinite(u_raw):
        u_raw = ff
        I_new = I_prev
    u = _clamp(u_raw, 0.0, 1.0)
    if yf > 0.85:
        u = 0.0
    elif yf > 0.80:
        if u > 0.15:
            u = 0.15
    if not math.isfinite(u):
        u = _clamp(ff, 0.0, 1.0)
    u = _clamp(float(u), 0.0, 1.0)
    new_state = {"yf": float(yf), "I": float(I_new)}
    return (u, new_state)
