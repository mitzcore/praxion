import math
def _clamp(v, lo, hi):
    if v < lo:
        return lo
    if v > hi:
        return hi
    return v
def control(obs, state):
    y = obs.get("y", 0.5)
    target = obs.get("target", 0.5)
    dt = obs.get("dt", 1.0)
    try:
        y = float(y)
    except:
        y = 0.5
    try:
        target = float(target)
    except:
        target = 0.5
    try:
        dt = float(dt)
    except:
        dt = 1.0
    if not math.isfinite(y):
        yf0 = state.get("yf", 0.5)
        try:
            yf0 = float(yf0)
        except:
            yf0 = 0.5
        if not math.isfinite(yf0):
            yf0 = 0.5
        y = yf0
    if not math.isfinite(target):
        target = 0.5
    if not math.isfinite(dt) or dt <= 0.0:
        dt = 1.0
    y = _clamp(y, 0.0, 1.0)
    target = _clamp(target, 0.0, 1.0)
    dtc = _clamp(dt, 0.2, 5.0)
    yf_prev = state.get("yf", y)
    try:
        yf_prev = float(yf_prev)
    except:
        yf_prev = y
    if not math.isfinite(yf_prev):
        yf_prev = y
    yf_prev = _clamp(yf_prev, 0.0, 1.0)
    tau_f = 8.0
    alpha = dtc / (tau_f + dtc)
    yf = alpha * y + (1.0 - alpha) * yf_prev
    if not math.isfinite(yf):
        yf = yf_prev
    yf = _clamp(yf, 0.0, 1.0)
    e = target - yf
    y_amb = 0.05
    gain = 0.99
    u_ff = (target - y_amb) / gain
    u_ff = _clamp(u_ff, 0.0, 0.8)
    Kp = 1.8
    Ki = 0.015
    I_prev = state.get("I", 0.0)
    try:
        I_prev = float(I_prev)
    except:
        I_prev = 0.0
    if not math.isfinite(I_prev):
        I_prev = 0.0
    I_prev = _clamp(I_prev, -10.0, 10.0)
    if abs(e) < 0.10:
        I_prop = I_prev + e * dtc
    else:
        I_prop = I_prev
    I_prop = _clamp(I_prop, -10.0, 10.0)
    u_unsat = u_ff + Kp * e + Ki * I_prop
    if not math.isfinite(u_unsat):
        u_unsat = u_ff
    u = _clamp(u_unsat, 0.0, 0.75)
    if (u >= 0.75 and e > 0.0) or (u <= 0.0 and e < 0.0):
        I_new = I_prev
    else:
        I_new = I_prop
    if yf > 0.80 or y > 0.85:
        u = 0.0
        if I_new > 0.0:
            I_new = 0.0
    u = _clamp(u, 0.0, 1.0)
    if not math.isfinite(u):
        u = u_ff
    return (u, {"yf": yf, "I": I_new})
