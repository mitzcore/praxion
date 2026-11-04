import math

def _clamp(v, lo, hi):
    if v < lo:
        return lo
    if v > hi:
        return hi
    return v

def control(obs: dict, state: dict) -> tuple[float, dict]:
    if not isinstance(state, dict):
        state = {}
    try:
        y_in = obs.get("y", 0.5)
    except Exception:
        y_in = 0.5
    try:
        t_in = obs.get("target", 0.5)
    except Exception:
        t_in = 0.5
    try:
        dt_in = obs.get("dt", 1.0)
    except Exception:
        dt_in = 1.0
    try:
        y_raw = float(y_in)
    except Exception:
        y_raw = float('nan')
    try:
        target = float(t_in)
    except Exception:
        target = 0.5
    try:
        dt = float(dt_in)
    except Exception:
        dt = 1.0
    if not math.isfinite(target):
        target = 0.5
    if not math.isfinite(dt) or dt <= 0.0:
        dt = 1.0
    target = _clamp(target, 0.0, 1.0)
    if dt < 0.1:
        dt = 0.1
    if dt > 30.0:
        dt = 30.0
    # prior filter for coast on bad sensor
    yf_prev_raw = state.get("yf", None)
    try:
        yf_prev_f = float(yf_prev_raw) if yf_prev_raw is not None else float('nan')
    except Exception:
        yf_prev_f = float('nan')
    if not math.isfinite(yf_prev_f):
        yf_prev_f = float('nan')
    else:
        yf_prev_f = _clamp(yf_prev_f, 0.0, 1.0)
    if not math.isfinite(y_raw):
        if math.isfinite(yf_prev_f):
            y_raw = yf_prev_f
        else:
            y_raw = 0.5
    y_raw = _clamp(y_raw, 0.0, 1.0)
    tau_f = 12.0
    alpha = dt / (tau_f + dt)
    if not math.isfinite(yf_prev_f):
        yf = y_raw
    else:
        yf = yf_prev_f + alpha * (y_raw - yf_prev_f)
    yf = _clamp(yf, 0.0, 1.0)
    # adaptive hold-bias, init at nominal feedforward
    u_nom = 0.33 + (target - 0.5) / 1.1
    u_nom = _clamp(u_nom, 0.0, 0.85)
    b_raw = state.get("bias", None)
    if b_raw is None:
        # migrate legacy integ if present
        integ_legacy = state.get("integ", None)
        try:
            integ_f = float(integ_legacy) if integ_legacy is not None else None
        except Exception:
            integ_f = None
        if integ_f is not None and math.isfinite(integ_f):
            bias = _clamp(u_nom + _clamp(integ_f, -0.25, 0.25), 0.0, 0.85)
        else:
            bias = u_nom
    else:
        try:
            bias = float(b_raw)
        except Exception:
            bias = u_nom
        if not math.isfinite(bias):
            bias = u_nom
        bias = _clamp(bias, 0.0, 0.85)
    Kp = 0.90
    Ki = 0.020
    b_lo = 0.0
    b_hi = 0.85
    u_lo = 0.0
    u_hi = 0.85
    e = target - yf
    if e > 1.0:
        e = 1.0
    if e < -1.0:
        e = -1.0
    # slow adaptation gated to avoid windup on huge transient
    if abs(e) < 0.35:
        b_new = bias + Ki * e * dt
    else:
        b_new = bias
    b_new = _clamp(b_new, b_lo, b_hi)
    u_raw2 = b_new + Kp * e
    u = _clamp(u_raw2, u_lo, u_hi)
    # anti-windup: freeze if saturated and error would push further
    if (u_raw2 > u_hi and e > 0.0) or (u_raw2 < u_lo and e < 0.0):
        b_new = bias
        u_raw2 = b_new + Kp * e
        u = _clamp(u_raw2, u_lo, u_hi)
    if not math.isfinite(u):
        u = _clamp(bias, 0.0, 1.0)
        b_new = bias
    u = _clamp(float(u), 0.0, 1.0)
    new_state = {"yf": float(yf), "bias": float(b_new), "target": float(target)}
    return (float(u), new_state)
