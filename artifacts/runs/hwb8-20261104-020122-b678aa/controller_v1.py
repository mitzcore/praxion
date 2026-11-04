import math

def _clamp(v, lo, hi):
    if v < lo:
        return lo
    if v > hi:
        return hi
    return v

def control(obs, state):
    if not isinstance(state, dict):
        state = {}
    y_in = obs.get("y", 0.5)
    t_in = obs.get("target", 0.5)
    dt_in = obs.get("dt", 1.0)
    try:
        y_raw = float(y_in)
    except Exception:
        y_raw = 0.5
    try:
        target = float(t_in)
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
    y_raw = _clamp(y_raw, 0.0, 1.0)
    target = _clamp(target, 0.0, 1.0)
    if dt < 0.1:
        dt = 0.1
    if dt > 30.0:
        dt = 30.0
    yf_prev = state.get("yf", None)
    integ_prev = state.get("integ", 0.0)
    try:
        integ_prev = float(integ_prev)
    except Exception:
        integ_prev = 0.0
    if not math.isfinite(integ_prev):
        integ_prev = 0.0
    integ_prev = _clamp(integ_prev, -0.25, 0.25)
    tau_f = 12.0
    alpha = dt / (tau_f + dt)
    if yf_prev is None:
        try:
            yf_p = float(yf_prev) if yf_prev is not None else y_raw
        except Exception:
            yf_p = y_raw
        if not math.isfinite(yf_p):
            yf_p = y_raw
        yf = _clamp(yf_p, 0.0, 1.0)
        # initialize filter at measurement to avoid kick
        yf = y_raw
    else:
        try:
            yf_p = float(yf_prev)
        except Exception:
            yf_p = y_raw
        if not math.isfinite(yf_p):
            yf_p = y_raw
        yf_p = _clamp(yf_p, 0.0, 1.0)
        yf = yf_p + alpha * (y_raw - yf_p)
        yf = _clamp(yf, 0.0, 1.0)
    u_ff = 0.33 + (target - 0.5) / 1.1
    u_ff = _clamp(u_ff, 0.0, 0.70)
    Kp = 0.80
    Ki = 0.006
    e = target - yf
    if e > 1.0:
        e = 1.0
    if e < -1.0:
        e = -1.0
    if abs(e) < 0.20:
        integ_new = integ_prev + Ki * e * dt
        integ_new = _clamp(integ_new, -0.25, 0.25)
    else:
        integ_new = integ_prev
    P = Kp * e
    u_raw = u_ff + P + integ_new
    u_min = 0.0
    u_max = 0.70
    u = _clamp(u_raw, u_min, u_max)
    if (u_raw > u_max and e > 0.0) or (u_raw < u_min and e < 0.0):
        integ_new = integ_prev
        u_raw2 = u_ff + P + integ_new
        u = _clamp(u_raw2, u_min, u_max)
    u = _clamp(u, 0.0, 1.0)
    if not math.isfinite(u):
        u = _clamp(u_ff, 0.0, 1.0)
        integ_new = integ_prev
    new_state = {"yf": float(yf), "integ": float(integ_new)}
    return (float(u), new_state)
