import math
def _clamp(x, lo, hi):
    if x < lo:
        return lo
    if x > hi:
        return hi
    return x
def control(obs, state):
    KP = 0.35
    KI = 0.035
    KD = 2.5
    TAU_F = 2.0
    TAU_R = 3.0
    I_LIM = 5.0
    FF0 = 0.62
    INV_GAIN = 0.5
    T0 = 0.6
    RATE_UP = 0.25
    RATE_DOWN = 0.6
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
    bad_y = False
    if not math.isfinite(y_raw):
        bad_y = True
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
        yf_prev = float(state.get("yf", target if y_raw is None else _clamp(y_raw, 0.0, 1.0)))
    except Exception:
        yf_prev = target
    try:
        I_prev = float(state.get("I", 0.0))
    except Exception:
        I_prev = 0.0
    try:
        rate_prev = float(state.get("rate", 0.0))
    except Exception:
        rate_prev = 0.0
    try:
        u_prev = float(state.get("u_prev", FF0))
    except Exception:
        u_prev = FF0
    if not math.isfinite(yf_prev):
        yf_prev = target
    if not math.isfinite(I_prev):
        I_prev = 0.0
    if not math.isfinite(rate_prev):
        rate_prev = 0.0
    if not math.isfinite(u_prev):
        u_prev = FF0
    yf_prev = _clamp(yf_prev, 0.0, 1.0)
    I_prev = _clamp(I_prev, -I_LIM, I_LIM)
    rate_prev = _clamp(rate_prev, -0.2, 0.2)
    u_prev = _clamp(u_prev, 0.0, 1.0)
    if y_raw is None:
        y_meas = yf_prev
    else:
        y_meas = _clamp(y_raw, 0.0, 1.0)
    alpha = dt / (TAU_F + dt)
    yf = yf_prev + alpha * (y_meas - yf_prev)
    if not math.isfinite(yf):
        yf = yf_prev
    yf = _clamp(yf, 0.0, 1.0)
    if bad_y:
        yf = yf_prev
    rate_raw = (yf - yf_prev) / dt
    if not math.isfinite(rate_raw):
        rate_raw = 0.0
    rate_raw = _clamp(rate_raw, -0.2, 0.2)
    beta = dt / (TAU_R + dt)
    rate = rate_prev + beta * (rate_raw - rate_prev)
    if not math.isfinite(rate):
        rate = rate_prev
    rate = _clamp(rate, -0.2, 0.2)
    e = target - yf
    if not math.isfinite(e):
        e = 0.0
    e_p = _clamp(e, -0.4, 0.4)
    ff = FF0 + INV_GAIN * (target - T0)
    ff = _clamp(ff, 0.0, 0.85)
    p = KP * e_p
    I_try = I_prev + e * dt
    I_try = _clamp(I_try, -I_LIM, I_LIM)
    u_try = ff + p + KI * I_try - KD * rate
    saturated_hi = u_try > 1.0 and e > 0.0
    saturated_lo = u_try < 0.0 and e < 0.0
    if saturated_hi or saturated_lo:
        I_new = I_prev
        u_raw = ff + p + KI * I_new - KD * rate
    else:
        I_new = I_try
        u_raw = u_try
    if not math.isfinite(u_raw):
        u_raw = ff
        I_new = I_prev
    if not math.isfinite(I_new):
        I_new = I_prev
    I_new = _clamp(I_new, -I_LIM, I_LIM)
    u_raw = _clamp(u_raw, 0.0, 1.0)
    du = u_raw - u_prev
    if du > 0.0:
        max_up = RATE_UP * dt
        if du > max_up:
            du = max_up
    else:
        max_down = RATE_DOWN * dt
        if du < -max_down:
            du = -max_down
    u = u_prev + du
    u = _clamp(u, 0.0, 1.0)
    y_pred = yf + 6.0 * rate
    if yf > 0.82 or y_pred > 0.88:
        u = 0.0
    elif yf > 0.75 or y_pred > 0.82:
        if u > 0.15:
            u = 0.15
    elif yf > 0.70 and rate > 0.02:
        if u > 0.40:
            u = 0.40
    if not math.isfinite(u):
        u = _clamp(ff, 0.0, 1.0)
    u = _clamp(float(u), 0.0, 1.0)
    new_state = {"yf": float(yf), "I": float(I_new), "rate": float(rate), "u_prev": float(u)}
    return (u, new_state)
