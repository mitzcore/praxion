import math

def _clamp(v, lo, hi):
    if v < lo:
        return lo
    if v > hi:
        return hi
    return v

def control(obs, state):
    y_raw = obs.get("y", 0.5)
    target = obs.get("target", 0.5)
    dt_in = obs.get("dt", 1.0)
    try:
        y_raw = float(y_raw)
    except Exception:
        y_raw = 0.5
    try:
        target = float(target)
    except Exception:
        target = 0.5
    try:
        dt = float(dt_in)
    except Exception:
        dt = 1.0
    if not math.isfinite(y_raw):
        y_raw = 0.5
    if not math.isfinite(target):
        target = 0.5
    if not math.isfinite(dt) or dt <= 0.0:
        dt = 1.0
    if dt < 0.2:
        dt = 0.2
    if dt > 30.0:
        dt = 30.0
    if target < 0.0:
        target = 0.0
    if target > 1.0:
        target = 1.0
    if y_raw < -0.2:
        y_raw = -0.2
    if y_raw > 1.2:
        y_raw = 1.2
    AMB = 0.175
    K0 = 1.15
    KP = 1.0
    KI = 0.009
    KFF = 0.006
    TF = 12.0
    UMIN = 0.0
    UMAX = 0.80
    IMIN = -0.18
    IMAX = 0.32
    BMIN = -0.12
    BMAX = 0.40
    E_ENABLE = 0.15
    E_ADAPT = 0.12
    ff0 = (target - AMB) / K0
    ff0 = _clamp(ff0, 0.0, UMAX)
    yf_prev = state.get("yf", None)
    try:
        I_prev = float(state.get("I", 0.0))
    except Exception:
        I_prev = 0.0
    try:
        bias_prev = float(state.get("bias", 0.0))
    except Exception:
        bias_prev = 0.0
    u_prev_raw = state.get("u", None)
    if not math.isfinite(I_prev):
        I_prev = 0.0
    if not math.isfinite(bias_prev):
        bias_prev = 0.0
    I_prev = _clamp(I_prev, IMIN, IMAX)
    bias_prev = _clamp(bias_prev, BMIN, BMAX)
    if yf_prev is None:
        yf = _clamp(y_raw, 0.0, 1.0)
    else:
        try:
            yf_prev = float(yf_prev)
        except Exception:
            yf_prev = _clamp(y_raw, 0.0, 1.0)
        if not math.isfinite(yf_prev):
            yf_prev = _clamp(y_raw, 0.0, 1.0)
        alpha = dt / (TF + dt)
        diff = y_raw - yf_prev
        if diff > 0.07 or diff < -0.07:
            alpha = alpha * 0.25
        yf = yf_prev + alpha * diff
        if not math.isfinite(yf):
            yf = yf_prev
        if yf < 0.0:
            yf = 0.0
        if yf > 1.0:
            yf = 1.0
    e = target - yf
    P = KP * e
    I_new = I_prev
    if abs(e) < E_ENABLE and yf < 0.70:
        I_tent = I_prev + KI * e * dt
        I_tent = _clamp(I_tent, IMIN, IMAX)
        u_tent_c = ff0 + bias_prev + P + I_tent
        if u_tent_c > UMAX and e > 0.0:
            I_new = I_prev
        elif u_tent_c < UMIN and e < 0.0:
            I_new = I_prev
        else:
            I_new = I_tent
    if yf > 0.70 and I_new > 0.0:
        decay = 1.0 - dt / 120.0
        if decay < 0.0:
            decay = 0.0
        I_new = I_new * decay
    bias_new = bias_prev
    if abs(e) < E_ADAPT and yf < 0.70:
        b_tent = bias_prev + KFF * e * dt
        b_tent = _clamp(b_tent, BMIN, BMAX)
        u_tent_b = ff0 + b_tent + P + I_new
        if u_tent_b > UMAX and e > 0.0:
            bias_new = bias_prev
        elif u_tent_b < UMIN and e < 0.0:
            bias_new = bias_prev
        else:
            bias_new = b_tent
    u_dem = ff0 + bias_new + P + I_new
    u_dem = _clamp(u_dem, UMIN, UMAX)
    if u_prev_raw is None:
        u = u_dem
    else:
        try:
            u_prev_f = float(u_prev_raw)
        except Exception:
            u_prev_f = u_dem
        if not math.isfinite(u_prev_f):
            u_prev_f = u_dem
        u_prev_f = _clamp(u_prev_f, UMIN, UMAX)
        beta = dt / (2.5 + dt)
        u = u_prev_f + beta * (u_dem - u_prev_f)
        u = _clamp(u, UMIN, UMAX)
    if yf > 0.75:
        u = 0.0
        if I_new > -0.05:
            I_new = -0.05
    if y_raw > 0.85:
        u = 0.0
    if not math.isfinite(u):
        u = _clamp(ff0 + bias_new, UMIN, UMAX)
    u = _clamp(u, 0.0, 1.0)
    new_state = {"yf": float(yf), "I": float(I_new), "bias": float(bias_new), "u": float(u)}
    return (float(u), new_state)
