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
    if not isinstance(state, dict):
        state = {}
    try:
        y_raw = obs.get("y", 0.6)
    except Exception:
        y_raw = 0.6
    try:
        t_raw = obs.get("target", 0.6)
    except Exception:
        t_raw = 0.6
    try:
        dt_raw = obs.get("dt", 0.2)
    except Exception:
        dt_raw = 0.2
    try:
        dt = float(dt_raw)
    except Exception:
        dt = 0.2
    if not math.isfinite(dt) or dt <= 0.0:
        dt = 0.2
    if dt < 0.05:
        dt = 0.05
    if dt > 2.5:
        dt = 2.5
    try:
        target = float(t_raw)
    except Exception:
        target = 0.6
    if not math.isfinite(target):
        target = 0.6
    target = _clamp(target, 0.0, 0.85)
    try:
        y = float(y_raw)
    except Exception:
        y = float("nan")
    try:
        yf_prev = float(state.get("yf", float("nan")))
    except Exception:
        yf_prev = float("nan")
    try:
        yd_prev = float(state.get("yd", 0.0))
    except Exception:
        yd_prev = 0.0
    if not math.isfinite(yd_prev):
        yd_prev = 0.0
    yd_prev = _clamp(yd_prev, -0.1, 0.1)
    if not math.isfinite(y):
        if math.isfinite(yf_prev):
            y = yf_prev
        else:
            y = target
    y = _clamp(y, 0.0, 1.0)
    if not math.isfinite(yf_prev):
        yf = y
        yd = 0.0
    else:
        yf_prev = _clamp(yf_prev, 0.0, 1.0)
        tau_f = 2.0
        a = dt / (tau_f + dt)
        yf = yf_prev + a * (y - yf_prev)
        yf = _clamp(yf, 0.0, 1.0)
        try:
            raw = (yf - yf_prev) / dt
        except Exception:
            raw = 0.0
        if not math.isfinite(raw):
            raw = 0.0
        raw = _clamp(raw, -0.1, 0.1)
        tau_d = 3.0
        ad = dt / (tau_d + dt)
        yd = yd_prev + ad * (raw - yd_prev)
        yd = _clamp(yd, -0.1, 0.1)
    try:
        integ_prev = float(state.get("integ", 0.0))
    except Exception:
        integ_prev = 0.0
    if not math.isfinite(integ_prev):
        integ_prev = 0.0
    try:
        ff_a = float(state.get("ffa", float("nan")))
    except Exception:
        ff_a = float("nan")
    ff_base = 0.297 + target / 2.72
    ff_base = _clamp(ff_base, 0.15, 0.75)
    if not math.isfinite(ff_a):
        ff_a = ff_base
    ff_a = _clamp(ff_a, 0.30, 0.70)
    try:
        ss = float(state.get("slow_score", 0.0))
    except Exception:
        ss = 0.0
    if not math.isfinite(ss):
        ss = 0.0
    ss = _clamp(ss, 0.0, 30.0)
    try:
        slow = int(state.get("slow", 0))
    except Exception:
        slow = 0
    if slow not in (0, 1):
        slow = 0
    try:
        u_prev = float(state.get("u_prev", float("nan")))
    except Exception:
        u_prev = float("nan")
    if not math.isfinite(u_prev):
        u_prev = ff_a
    u_prev = _clamp(u_prev, 0.0, 1.0)
    ff = ff_a
    e = target - yf
    e = _clamp(e, -1.0, 1.0)
    drive = u_prev - ff
    if abs(e) > 0.06 and abs(drive) > 0.07 and abs(yd) < 0.005:
        ss = ss + dt
    else:
        ss = ss - dt * 0.5
    ss = _clamp(ss, 0.0, 30.0)
    if slow == 0 and ss > 8.0:
        slow = 1
    if slow == 0:
        Kp = 0.45
        Ki = 0.055
        IMAX = 0.20
        UMAX = 0.82
        slew = 0.25
        Td = 3.0
    else:
        Kp = 0.16
        Ki = 0.012
        IMAX = 0.15
        UMAX = 0.68
        slew = 0.04
        Td = 22.0
    integ_prev = _clamp(integ_prev, -IMAX, IMAX)
    P = Kp * e
    integ = integ_prev
    if abs(e) < 0.20:
        integ = integ_prev + Ki * e * dt
        integ = _clamp(integ, -IMAX, IMAX)
    u_test = ff + P + integ
    if (u_test > UMAX and e > 0.0) or (u_test < 0.0 and e < 0.0):
        integ = integ_prev
    u_unsat = ff + P + integ
    max_du = slew * dt
    if max_du < 0.005:
        max_du = 0.005
    du = u_unsat - u_prev
    if du > max_du:
        du = max_du
    elif du < -max_du:
        du = -max_du
    u = u_prev + du
    if yf > 0.55 and math.isfinite(yd) and yd > 0.0:
        y_pred = yf + yd * Td
        if y_pred > 0.78:
            if u > 0.20:
                u = 0.20
        elif y_pred > 0.72:
            if u > 0.35:
                u = 0.35
        elif y_pred > 0.68:
            if u > 0.50:
                u = 0.50
    if yf > 0.80:
        u = 0.0
        if integ > -0.05:
            integ = -0.05
    elif yf > 0.75:
        if u > 0.25:
            u = 0.25
        if integ > 0.0:
            integ = 0.0
    u = _clamp(u, 0.0, 1.0)
    if abs(e) < 0.05:
        beta = dt / 30.0
        if beta > 1.0:
            beta = 1.0
        ff_a = ff_a + beta * (u_prev - ff_a)
        ff_a = _clamp(ff_a, 0.30, 0.70)
    new_state = {"yf": float(yf), "yd": float(yd), "integ": float(integ), "ffa": float(ff_a), "slow_score": float(ss), "slow": int(slow), "u_prev": float(u)}
    return (float(u), new_state)
