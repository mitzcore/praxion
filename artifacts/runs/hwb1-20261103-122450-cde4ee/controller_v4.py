import math
def _clamp(v, lo, hi):
    if v < lo:
        return lo
    if v > hi:
        return hi
    return v
def control(obs, state):
    y_raw_in = obs.get("y", 0.5)
    target_in = obs.get("target", 0.5)
    dt_in = obs.get("dt", 1.0)
    try:
        y_raw_t = float(y_raw_in)
    except Exception:
        y_raw_t = float('nan')
    try:
        target = float(target_in)
    except Exception:
        target = 0.5
    try:
        dt = float(dt_in)
    except Exception:
        dt = 1.0
    if not math.isfinite(target):
        target = 0.5
    target = _clamp(target, 0.0, 1.0)
    if not math.isfinite(dt) or dt <= 0.0:
        dt = 1.0
    dt = _clamp(dt, 0.2, 30.0)
    AMB = 0.17
    K_NOM = 1.15
    KMIN = 0.35
    KMAX = 1.60
    KP0 = 1.10
    KI0 = 0.020
    TF = 8.0
    TAVG = 60.0
    TADAPT = 55.0
    UMIN = 0.0
    UMAX = 0.85
    IMIN = -0.20
    IMAX = 0.50
    try:
        yf_prev = state.get("yf", None)
        if yf_prev is not None:
            yf_prev = float(yf_prev)
            if not math.isfinite(yf_prev):
                yf_prev = None
    except Exception:
        yf_prev = None
    try:
        I_prev = float(state.get("I", 0.0))
    except Exception:
        I_prev = 0.0
    try:
        Kest_prev = float(state.get("Kest", K_NOM))
    except Exception:
        Kest_prev = K_NOM
    try:
        y_avg_prev = state.get("y_avg", None)
        if y_avg_prev is not None:
            y_avg_prev = float(y_avg_prev)
            if not math.isfinite(y_avg_prev):
                y_avg_prev = None
    except Exception:
        y_avg_prev = None
    try:
        u_avg_prev = state.get("u_avg", None)
        if u_avg_prev is not None:
            u_avg_prev = float(u_avg_prev)
            if not math.isfinite(u_avg_prev):
                u_avg_prev = None
    except Exception:
        u_avg_prev = None
    try:
        t_prev = float(state.get("t", 0.0))
        if not math.isfinite(t_prev):
            t_prev = 0.0
    except Exception:
        t_prev = 0.0
    try:
        u_prev_raw = state.get("u", None)
        if u_prev_raw is not None:
            u_prev_raw = float(u_prev_raw)
            if not math.isfinite(u_prev_raw):
                u_prev_raw = None
    except Exception:
        u_prev_raw = None
    if not math.isfinite(I_prev):
        I_prev = 0.0
    I_prev = _clamp(I_prev, IMIN, IMAX)
    if not math.isfinite(Kest_prev):
        Kest_prev = K_NOM
    Kest_prev = _clamp(Kest_prev, KMIN, KMAX)
    if t_prev < 0.0 or t_prev > 1e7:
        t_prev = 0.0
    if not math.isfinite(y_raw_t):
        if yf_prev is not None:
            y_raw = float(yf_prev)
        else:
            y_raw = 0.5
    else:
        y_raw = float(y_raw_t)
        if y_raw < -0.2:
            y_raw = -0.2
        if y_raw > 1.2:
            y_raw = 1.2
    if yf_prev is None:
        yf = _clamp(y_raw, 0.0, 1.0)
    else:
        alpha = dt / (TF + dt)
        diff = y_raw - yf_prev
        if diff > 0.07 or diff < -0.07:
            alpha = alpha * 0.25
        yf = yf_prev + alpha * diff
        if not math.isfinite(yf):
            yf = yf_prev
        yf = _clamp(yf, 0.0, 1.0)
    if y_avg_prev is None:
        y_avg = float(yf)
    else:
        y_avg = float(y_avg_prev)
    if not math.isfinite(y_avg):
        y_avg = float(yf)
    if u_avg_prev is None:
        ff0 = (target - AMB) / Kest_prev
        u_avg = _clamp(ff0, 0.0, UMAX)
    else:
        u_avg = float(u_avg_prev)
    if not math.isfinite(u_avg):
        u_avg = 0.28
    u_avg = _clamp(u_avg, 0.0, 1.0)
    t_new = t_prev + dt
    a = dt / (TAVG + dt)
    y_avg = y_avg + a * (yf - y_avg)
    if u_prev_raw is None:
        u_for_avg = float(u_avg)
    else:
        u_for_avg = _clamp(float(u_prev_raw), UMIN, UMAX)
    u_avg = u_avg + a * (u_for_avg - u_avg)
    u_avg = _clamp(u_avg, 0.0, 1.0)
    Kest = float(Kest_prev)
    if t_new > 60.0 and yf < 0.75 and y_avg > 0.22 and y_avg < 0.72 and u_avg > 0.12:
        if abs(yf - y_avg) < 0.02:
            denom = u_avg if u_avg >= 0.08 else 0.08
            Kobs = (y_avg - AMB) / denom
            Kobs = _clamp(Kobs, KMIN, KMAX)
            rate = dt / TADAPT
            if rate > 1.0:
                rate = 1.0
            Kest = Kest + rate * (Kobs - Kest)
            Kest = _clamp(Kest, KMIN, KMAX)
    if not math.isfinite(Kest):
        Kest = Kest_prev
    ff = (target - AMB) / Kest if Kest > 0.05 else UMAX
    ff = _clamp(ff, 0.0, UMAX)
    scale = K_NOM / Kest if Kest > 0.05 else 1.9
    scale = _clamp(scale, 0.8, 1.9)
    KP = KP0 * scale
    KI = KI0 * scale
    e = target - yf
    I_new = float(I_prev)
    if abs(e) < 0.20 and yf < 0.72:
        I_tent = I_prev + KI * e * dt
        I_tent = _clamp(I_tent, IMIN, IMAX)
        u_tent = ff + KP * e + I_tent
        if u_tent > UMAX and e > 0.0:
            I_new = I_prev
        elif u_tent < UMIN and e < 0.0:
            I_new = I_prev
        else:
            I_new = I_tent
    if yf > 0.70 and I_new > 0.0:
        decay = 1.0 - dt / 120.0
        if decay < 0.0:
            decay = 0.0
        I_new = I_new * decay
    P = KP * e
    u_dem = ff + P + I_new
    u_dem = _clamp(u_dem, UMIN, UMAX)
    if u_prev_raw is None:
        u = float(u_dem)
    else:
        u_pf = _clamp(float(u_prev_raw), UMIN, UMAX)
        beta = dt / (1.5 + dt)
        u = u_pf + beta * (u_dem - u_pf)
        u = _clamp(u, UMIN, UMAX)
    if yf > 0.75:
        u = 0.0
        if I_new > -0.05:
            I_new = -0.05
    if y_raw > 0.85:
        u = 0.0
    if not math.isfinite(u):
        u = _clamp(ff + I_new, UMIN, UMAX)
    u = _clamp(u, 0.0, 1.0)
    new_state = {"yf": float(yf), "I": float(I_new), "Kest": float(Kest), "y_avg": float(y_avg), "u_avg": float(u_avg), "t": float(t_new), "u": float(u)}
    return (float(u), new_state)
