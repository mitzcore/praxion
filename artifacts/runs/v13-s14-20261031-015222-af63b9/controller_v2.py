import math

def _clamp(x, lo, hi):
    if x < lo:
        return lo
    if x > hi:
        return hi
    return x

def _fin(x, d):
    try:
        f = float(x)
    except Exception:
        return d
    if not math.isfinite(f):
        return d
    return f

def control(obs, state):
    y_raw = _clamp(_fin(obs.get("y", 0.6), 0.6), 0.0, 1.0)
    target = _clamp(_fin(obs.get("target", 0.6), 0.6), 0.0, 1.0)
    dt = _clamp(_fin(obs.get("dt", 0.1), 0.1), 0.02, 1.0)
    TAU_F = 2.5
    KP_NEAR = 0.28
    KP_FAR = 0.70
    KI = 0.012
    I_MAX = 0.18
    KF = 0.005
    FF_MIN = 0.45
    FF_MAX = 0.70
    try:
        yf_prev = _clamp(_fin(state.get("yf", y_raw), y_raw), 0.0, 1.0)
    except Exception:
        yf_prev = y_raw
    try:
        I_prev = _clamp(_fin(state.get("I", 0.0), 0.0), -I_MAX, I_MAX)
    except Exception:
        I_prev = 0.0
    try:
        ff_prev = _clamp(_fin(state.get("ff", 0.59), 0.59), FF_MIN, FF_MAX)
    except Exception:
        ff_prev = 0.59
    try:
        u_prev = _fin(state.get("u_prev", float("nan")), float("nan"))
        if not math.isfinite(u_prev):
            u_prev = float("nan")
        else:
            u_prev = _clamp(u_prev, 0.0, 1.0)
    except Exception:
        u_prev = float("nan")
    is_first = ("yf" not in state)
    if is_first:
        yf = y_raw
        I = 0.0
        ff = 0.59
    else:
        alpha = dt / (TAU_F + dt)
        if not math.isfinite(alpha):
            alpha = 0.05
        alpha = _clamp(alpha, 0.0, 1.0)
        yf = (1.0 - alpha) * yf_prev + alpha * y_raw
        yf = _clamp(yf, 0.0, 1.0)
        e_tmp = target - yf
        e_tmp = _clamp(e_tmp, -1.0, 1.0)
        ff = ff_prev
        if abs(e_tmp) < 0.10 and 0.30 <= yf <= 0.80:
            ff = ff_prev + KF * e_tmp * dt
            ff = _clamp(ff, FF_MIN, FF_MAX)
        I = I_prev
        if abs(e_tmp) <= 0.20:
            I = I_prev + KI * e_tmp * dt
            I = _clamp(I, -I_MAX, I_MAX)
    e = target - yf
    e = _clamp(e, -1.0, 1.0)
    ae = abs(e)
    if ae < 0.0:
        ae = 0.0
    w = ae / 0.18
    if w > 1.0:
        w = 1.0
    Kp = KP_NEAR + (KP_FAR - KP_NEAR) * w
    P = Kp * e
    P = _clamp(P, -0.5, 0.5)
    u_raw = ff + P + I
    if not math.isfinite(u_raw):
        u_raw = ff
    if yf > 0.78:
        cap = 0.25
    elif yf > 0.72:
        cap = 0.40
    elif yf > 0.68:
        cap = 0.55
    elif yf > 0.64:
        cap = 0.70
    else:
        cap = 1.0
    u_capped = u_raw
    if u_capped > cap:
        u_capped = cap
    u_des = _clamp(u_capped, 0.0, 1.0)
    sat_high = (u_raw > cap + 1e-9) or (u_raw > 1.0 + 1e-9)
    sat_low = (u_raw < 0.0 - 1e-9)
    if not is_first:
        if (sat_high and e > 0.0) or (sat_low and e < 0.0):
            I = I_prev
            ff = ff_prev
            u_raw2 = ff + P + I
            if math.isfinite(u_raw2):
                if u_raw2 > cap:
                    u_raw2 = cap
                u_des = _clamp(u_raw2, 0.0, 1.0)
    if is_first or (not math.isfinite(u_prev)):
        u = u_des
    else:
        max_up = 0.035 + 0.15 * w
        if yf > 0.70:
            max_down = 0.60
        else:
            max_down = 0.06 + 0.10 * w
        du = u_des - u_prev
        if du > 0.0:
            lim = max_up * dt
            if du > lim:
                du = lim
        else:
            lim = max_down * dt
            if du < -lim:
                du = -lim
        u = u_prev + du
        u = _clamp(u, 0.0, 1.0)
    if not math.isfinite(u):
        u = _clamp(ff, 0.0, 1.0)
    u = _clamp(float(u), 0.0, 1.0)
    ns = {"yf": float(yf), "I": float(I), "ff": float(ff), "u_prev": float(u)}
    return (u, ns)
