import math
def _clamp(v, lo, hi):
    if not math.isfinite(v):
        return lo
    if v < lo:
        return lo
    if v > hi:
        return hi
    return v
def control(obs, state):
    try:
        y_raw = float(obs.get("y", 0.6))
    except Exception:
        y_raw = 0.6
    try:
        target = float(obs.get("target", 0.6))
    except Exception:
        target = 0.6
    try:
        dt = float(obs.get("dt", 0.1))
    except Exception:
        dt = 0.1
    if not math.isfinite(y_raw):
        y_raw = 0.6
    if not math.isfinite(target):
        target = 0.6
    if not math.isfinite(dt) or dt <= 0.0:
        dt = 0.1
    if dt < 0.02:
        dt = 0.02
    if dt > 0.5:
        dt = 0.5
    y_raw = _clamp(y_raw, 0.0, 1.0)
    target = _clamp(target, 0.0, 1.0)
    try:
        yf_prev = float(state.get("yf", y_raw))
    except Exception:
        yf_prev = y_raw
    try:
        integ_prev = float(state.get("integ", 0.0))
    except Exception:
        integ_prev = 0.0
    try:
        u_prev = float(state.get("u_prev", 0.53))
    except Exception:
        u_prev = 0.53
    if not math.isfinite(yf_prev):
        yf_prev = y_raw
    if not math.isfinite(integ_prev):
        integ_prev = 0.0
    if not math.isfinite(u_prev):
        u_prev = 0.53
    yf_prev = _clamp(yf_prev, 0.0, 1.0)
    integ_prev = _clamp(integ_prev, -0.25, 0.25)
    u_prev = _clamp(u_prev, 0.0, 1.0)
    # filter: tau 0.8 s
    tau_f = 0.8
    alpha = dt / (tau_f + dt)
    yf = yf_prev + alpha * (y_raw - yf_prev)
    yf = _clamp(yf, 0.0, 1.0)
    e = target - yf
    # feedforward: hold ~0.883*target (0.53 at 0.6)
    ff = 0.883 * target
    ff = _clamp(ff, 0.0, 0.8)
    Kp = 0.9
    Ki = 0.10
    P = Kp * e
    integ_new = integ_prev + Ki * e * dt
    integ_new = _clamp(integ_new, -0.25, 0.25)
    u_unsat = ff + P + integ_new
    # conditional anti-windup: freeze if saturated and pushing deeper
    if (u_unsat > 1.0 and e > 0.0) or (u_unsat < 0.0 and e < 0.0):
        integ_new = integ_prev
        u_unsat = ff + P + integ_new
    u = _clamp(u_unsat, 0.0, 1.0)
    # slew limit 1.0/s for smoothness
    max_du = 1.0 * dt
    du = u - u_prev
    if du > max_du:
        u = u_prev + max_du
    elif du < -max_du:
        u = u_prev - max_du
    # safety caps well below hard cutoff
    if yf > 0.82 or y_raw > 0.86:
        u = 0.0
    elif yf > 0.75:
        if u > 0.25:
            u = 0.25
    u = _clamp(u, 0.0, 1.0)
    if not math.isfinite(u):
        u = ff
        u = _clamp(u, 0.0, 1.0)
    state["yf"] = float(yf)
    state["integ"] = float(integ_new)
    state["u_prev"] = float(u)
    return (float(u), state)
