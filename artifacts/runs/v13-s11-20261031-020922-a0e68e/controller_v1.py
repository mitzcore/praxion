import math
def _clamp(v, lo, hi):
    if not math.isfinite(v):
        return lo
    if v < lo:
        return lo
    if v > hi:
        return hi
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
    if not math.isfinite(y):
        y = 0.6
    if not math.isfinite(target):
        target = 0.6
    if not math.isfinite(dt) or dt <= 0.0:
        dt = 0.1
    if dt < 0.02:
        dt = 0.02
    if dt > 1.0:
        dt = 1.0
    if y < 0.0:
        y = 0.0
    if y > 1.0:
        y = 1.0
    if target < 0.0:
        target = 0.0
    if target > 1.0:
        target = 1.0
    yf = state.get("yf", None)
    integ = state.get("i", 0.0)
    if yf is None or not math.isfinite(yf):
        yf = y
    if not math.isfinite(integ):
        integ = 0.0
    tau_f = 1.0
    alpha = dt / (tau_f + dt)
    if alpha < 0.0:
        alpha = 0.0
    if alpha > 1.0:
        alpha = 1.0
    yf = yf + alpha * (y - yf)
    if yf < 0.0:
        yf = 0.0
    if yf > 1.0:
        yf = 1.0
    if target <= 0.01:
        u_ff = 0.0
    else:
        r = target / 0.6
        if r < 0.0:
            r = 0.0
        u_ff = 0.50 * math.pow(r, 0.30)
    u_ff = _clamp(u_ff, 0.0, 0.80)
    Kp = 0.80
    Ki = 0.12
    e = target - yf
    enable = 0.25
    if abs(e) < enable:
        integ = integ + e * dt
    else:
        integ = integ * (1.0 - 0.05 * dt)
    max_i = 0.35 / Ki
    if integ > max_i:
        integ = max_i
    if integ < -max_i:
        integ = -max_i
    ui = Ki * integ
    if ui > 0.35:
        ui = 0.35
        integ = ui / Ki
    if ui < -0.35:
        ui = -0.35
        integ = ui / Ki
    u_unsat = u_ff + Kp * e + ui
    if yf >= 0.80:
        u_max = 0.10
    elif yf >= 0.75:
        u_max = 0.40
    elif yf >= 0.70:
        u_max = 0.60
    else:
        u_max = 0.95
    u_min = 0.0
    u = u_unsat
    if u > u_max:
        u = u_max
    if u < u_min:
        u = u_min
    if ((u >= u_max and e > 0.0) or (u <= u_min and e < 0.0)) and abs(e) < enable:
        pass
    u = _clamp(u, 0.0, 1.0)
    if not math.isfinite(u):
        u = u_ff
    new_state = {"yf": float(yf), "i": float(integ)}
    return (float(u), new_state)
