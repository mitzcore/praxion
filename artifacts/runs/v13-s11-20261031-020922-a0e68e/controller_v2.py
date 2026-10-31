import math
def _clamp(v, lo, hi):
    if not math.isfinite(v):
        return float(lo)
    if v < lo:
        return float(lo)
    if v > hi:
        return float(hi)
    return float(v)

def control(obs, state):
    try:
        y = obs.get("y", 0.6)
        target = obs.get("target", 0.6)
        dt = obs.get("dt", 0.1)
    except Exception:
        y = 0.6
        target = 0.6
        dt = 0.1
    if not math.isfinite(dt) or dt <= 0.0:
        dt = 0.1
    if dt < 0.02:
        dt = 0.02
    if dt > 1.0:
        dt = 1.0
    if not math.isfinite(target):
        target = 0.6
    target = _clamp(target, 0.0, 1.0)
    try:
        yf = state.get("yf", None)
        integ = state.get("i", 0.0)
        u_prev = state.get("up", None)
    except Exception:
        yf = None
        integ = 0.0
        u_prev = None
    if yf is None or not math.isfinite(yf):
        if math.isfinite(y):
            yf = _clamp(y, 0.0, 1.0)
        else:
            yf = 0.6
    if not math.isfinite(integ):
        integ = 0.0
    if u_prev is not None and not math.isfinite(u_prev):
        u_prev = None
    if math.isfinite(y):
        yc = _clamp(y, 0.0, 1.0)
    else:
        yc = float(yf)
    tau_f = 2.0
    alpha = dt / (tau_f + dt)
    if alpha < 0.0:
        alpha = 0.0
    if alpha > 1.0:
        alpha = 1.0
    yf = yf + alpha * (yc - yf)
    yf = _clamp(yf, 0.0, 1.0)
    if target <= 0.01:
        u_ff = 0.0
    else:
        r = target / 0.6
        if r < 0.0:
            r = 0.0
        if r > 1.7:
            r = 1.7
        u_ff = 0.54 * math.pow(r, 0.40)
    u_ff = _clamp(u_ff, 0.0, 0.80)
    Kp = 0.22
    Ki = 0.018
    e = target - yf
    integ_before = float(integ)
    if abs(e) < 0.12:
        integ = integ + e * dt
    else:
        integ = integ * (1.0 - 0.02 * dt)
    max_i = 0.18 / Ki
    if integ > max_i:
        integ = max_i
    if integ < -max_i:
        integ = -max_i
    ui = Ki * integ
    if ui > 0.18:
        ui = 0.18
        integ = ui / Ki
    if ui < -0.18:
        ui = -0.18
        integ = ui / Ki
    up = Kp * e
    if up > 0.20:
        up = 0.20
    if up < -0.20:
        up = -0.20
    u_t = u_ff + up + ui
    hi_ff = u_ff + 0.20
    lo_ff = u_ff - 0.30
    if u_t > hi_ff:
        u_t = hi_ff
    if u_t < lo_ff:
        u_t = lo_ff
    if yf >= 0.80:
        u_max = 0.05
    elif yf >= 0.75:
        u_max = 0.20
    elif yf >= 0.70:
        u_max = 0.35
    elif yf >= 0.65:
        u_max = 0.50
    else:
        u_max = 0.85
    u_targ = u_t
    if u_targ > u_max:
        u_targ = u_max
    if u_targ < 0.0:
        u_targ = 0.0
    u_targ = _clamp(u_targ, 0.0, 1.0)
    if u_prev is None:
        u = float(u_targ)
    else:
        u_prev = _clamp(float(u_prev), 0.0, 1.0)
        delta = u_targ - u_prev
        up_lim = 0.05 * dt
        dn_lim = 0.10 * dt
        if delta > up_lim:
            delta = up_lim
        if delta < -dn_lim:
            delta = -dn_lim
        u = u_prev + delta
        u = _clamp(u, 0.0, 1.0)
        saturated = False
        if u_t > u_max + 1e-9 or u_t < 0.0 - 1e-9:
            saturated = True
        if abs(delta - (u_targ - u_prev)) > 1e-9:
            if (e > 0.0 and u_targ > u_prev) or (e < 0.0 and u_targ < u_prev):
                saturated = True
        if saturated:
            if (e > 0.0 and u_targ >= u) or (e < 0.0 and u_targ <= u):
                integ = integ_before
                ui = Ki * integ
    if not math.isfinite(u):
        u = float(u_ff)
        integ = integ_before
    new_state = {"yf": float(yf), "i": float(integ), "up": float(_clamp(u, 0.0, 1.0))}
    return (float(_clamp(u, 0.0, 1.0)), new_state)
