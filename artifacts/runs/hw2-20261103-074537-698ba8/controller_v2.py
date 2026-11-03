import math
def _clamp(x, lo, hi):
    if x < lo:
        return lo
    if x > hi:
        return hi
    return x
def control(obs: dict, state: dict) -> tuple[float, dict]:
    AMB = 0.15
    GAIN = 1.08
    KP = 0.70
    KI = 0.015
    TAUF = 10.0
    UMAX = 0.78
    I_AUTH = 0.40
    E_GATE = 0.25
    if not isinstance(state, dict):
        state = {}
    try:
        y_raw = float(obs.get("y", 0.5))
    except:
        y_raw = 0.5
    try:
        target = float(obs.get("target", 0.5))
    except:
        target = 0.5
    try:
        dt = float(obs.get("dt", 1.0))
    except:
        dt = 1.0
    if not math.isfinite(y_raw):
        y_raw = 0.5
    if not math.isfinite(target):
        target = 0.5
    if not math.isfinite(dt) or dt <= 0.0:
        dt = 1.0
    if dt < 0.05:
        dt = 0.05
    if dt > 5.0:
        dt = 5.0
    target = _clamp(target, 0.0, 1.0)
    y_raw = _clamp(y_raw, 0.0, 1.0)
    yf_prev = state.get("yf", None)
    i_prev = state.get("i", 0.0)
    try:
        i_prev = float(i_prev)
    except:
        i_prev = 0.0
    if not math.isfinite(i_prev):
        i_prev = 0.0
    IMAX = I_AUTH / KI
    if IMAX > 100.0:
        IMAX = 100.0
    i_prev = _clamp(i_prev, -IMAX, IMAX)
    if yf_prev is None:
        yf = y_raw
    else:
        try:
            yf_prev = float(yf_prev)
        except:
            yf_prev = y_raw
        if not math.isfinite(yf_prev):
            yf_prev = y_raw
        yf_prev = _clamp(yf_prev, 0.0, 1.0)
        diff = y_raw - yf_prev
        if diff < -0.04:
            yf = yf_prev
        elif diff > 0.05:
            alpha = dt / (TAUF + dt)
            yf = yf_prev + alpha * 0.3 * diff
        else:
            alpha = dt / (TAUF + dt)
            yf = yf_prev + alpha * diff
        yf = _clamp(yf, 0.0, 1.0)
    ff = (target - AMB) / GAIN
    ff = _clamp(ff, 0.0, UMAX)
    e = target - yf
    i_new = i_prev
    if abs(e) < E_GATE:
        cand = i_prev + e * dt
        cand = _clamp(cand, -IMAX, IMAX)
        u_unsat = ff + KP * e + KI * cand
        if u_unsat > UMAX and e > 0.0:
            i_new = i_prev
        elif u_unsat < 0.0 and e < 0.0:
            i_new = i_prev
        else:
            if yf > 0.80 and e < 0.0:
                i_new = i_prev
            else:
                i_new = cand
    else:
        i_new = i_prev
    if yf > 0.80 and e < 0.0:
        i_new = i_prev
    u = ff + KP * e + KI * i_new
    u = _clamp(u, 0.0, UMAX)
    if yf > 0.80:
        u = min(u, 0.25)
    if y_raw > 0.88:
        u = 0.0
        i_new = i_prev
    if not math.isfinite(u):
        u = ff
        u = _clamp(u, 0.0, UMAX)
    new_state = {"yf": float(yf), "i": float(i_new)}
    return (float(u), new_state)
