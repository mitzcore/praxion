import math
def _clamp(v, lo, hi):
    if not math.isfinite(v):
        return lo
    if v < lo:
        return lo
    if v > hi:
        return hi
    return v
def _ff(t):
    if not math.isfinite(t):
        t = 0.6
    if t < 0.0:
        t = 0.0
    if t > 1.0:
        t = 1.0
    ff = 0.545 + (t - 0.6) * 1.0
    if ff < 0.30:
        ff = 0.30
    if ff > 0.75:
        ff = 0.75
    return ff
def control(obs, state):
    try:
        y_raw = obs.get("y", 0.6)
        tgt_raw = obs.get("target", 0.6)
        dt_raw = obs.get("dt", 0.2)
    except Exception:
        return (0.0, {"yf": 0.6, "i": 0.0, "up": 0.5, "df": 0.0})
    try:
        y = float(y_raw)
    except Exception:
        y = 0.6
    try:
        target = float(tgt_raw)
    except Exception:
        target = 0.6
    try:
        dt = float(dt_raw)
    except Exception:
        dt = 0.2
    if not math.isfinite(y):
        y = target if math.isfinite(target) else 0.6
    if not math.isfinite(target):
        target = 0.6
    if not math.isfinite(dt) or dt <= 0.0:
        dt = 0.2
    if dt < 0.02:
        dt = 0.02
    if dt > 1.0:
        dt = 1.0
    if y < -0.1:
        y = -0.1
    if y > 1.1:
        y = 1.1
    if target < 0.0:
        target = 0.0
    if target > 1.0:
        target = 1.0
    if not isinstance(state, dict):
        state = {}
    yf_p = state.get("yf", None)
    i_p = state.get("i", 0.0)
    up = state.get("up", None)
    df_p = state.get("df", 0.0)
    try:
        yf_p = float(yf_p) if yf_p is not None else y
    except Exception:
        yf_p = y
    try:
        i_p = float(i_p)
    except Exception:
        i_p = 0.0
    try:
        df_p = float(df_p)
    except Exception:
        df_p = 0.0
    try:
        up_f = float(up) if up is not None else None
    except Exception:
        up_f = None
    if not math.isfinite(yf_p):
        yf_p = _clamp(y, 0.0, 1.0)
    if not math.isfinite(i_p):
        i_p = 0.0
    if not math.isfinite(df_p):
        df_p = 0.0
    yf_p = _clamp(yf_p, 0.0, 1.0)
    i_p = _clamp(i_p, -0.12, 0.15)
    df_p = _clamp(df_p, -0.10, 0.10)
    if up_f is not None:
        if not math.isfinite(up_f):
            up_f = None
        else:
            up_f = _clamp(up_f, 0.0, 1.0)
    tau_f = 1.5
    alpha = dt / (tau_f + dt)
    if alpha < 0.02:
        alpha = 0.02
    if alpha > 1.0:
        alpha = 1.0
    yf = alpha * _clamp(y, 0.0, 1.0) + (1.0 - alpha) * yf_p
    yf = _clamp(yf, 0.0, 1.0)
    raw_slope = (yf - yf_p) / dt
    raw_slope = _clamp(raw_slope, -0.20, 0.20)
    df = 0.25 * raw_slope + 0.75 * df_p
    df = _clamp(df, -0.10, 0.10)
    e = target - yf
    ff = _ff(target)
    Kp = 0.40
    Ki = 0.05
    e_c = _clamp(e, -0.25, 0.35)
    p = Kp * e_c
    allow = True
    if abs(e) > 0.18:
        allow = False
    if yf >= 0.70:
        allow = False
    if yf <= 0.05:
        allow = False
    if allow:
        i_new = i_p + Ki * e * dt
    else:
        i_new = i_p * (1.0 - 0.02 * dt)
        if not math.isfinite(i_new):
            i_new = i_p
    i_new = _clamp(i_new, -0.12, 0.15)
    u_raw = ff + p + i_new
    u_raw = _clamp(u_raw, 0.0, 1.0)
    if up_f is None:
        u_rl = u_raw
    else:
        max_up = 0.15 * dt
        max_dn = 0.60 * dt
        if max_up < 0.005:
            max_up = 0.005
        if max_dn < 0.01:
            max_dn = 0.01
        if u_raw > up_f:
            du = u_raw - up_f
            if du > max_up:
                du = max_up
            u_rl = up_f + du
        elif u_raw < up_f:
            du = up_f - u_raw
            if du > max_dn:
                du = max_dn
            u_rl = up_f - du
        else:
            u_rl = up_f
    u_rl = _clamp(u_rl, 0.0, 1.0)
    y_pred = yf + df * 6.0
    cap = 1.0
    if yf >= 0.78:
        cap = 0.0
    elif yf >= 0.72:
        cap = 0.10
    elif yf >= 0.68:
        cap = 0.25
    if y_pred >= 0.75:
        if cap > 0.25:
            cap = 0.25
    elif y_pred >= 0.70:
        if cap > 0.40:
            cap = 0.40
    if yf > 0.62 and df > 0.015:
        if cap > 0.40:
            cap = 0.40
    u = u_rl
    if u > cap:
        u = cap
    u = _clamp(u, 0.0, 1.0)
    if not math.isfinite(u):
        u = 0.0
        i_new = 0.0
    return (float(u), {"yf": float(yf), "i": float(i_new), "up": float(u), "df": float(df)})
