import math
def _clamp(x, lo, hi):
    if x < lo:
        return lo
    if x > hi:
        return hi
    return x
def _ok(x):
    return isinstance(x, (int, float)) and math.isfinite(float(x))
def control(obs, state):
    Y_AMB = 0.08
    K_GAIN = 1.08
    KP = 0.9
    KI = 0.01
    KI_FAR = 0.002
    TF = 12.0
    I_LIM = 0.25
    P_LIM = 0.45
    U_LO = 0.0
    U_HI = 0.85
    ERR_FAR = 0.15
    ERR_DB = 0.002
    if state is None:
        state = {}
    y_raw = obs.get("y", 0.5)
    target = obs.get("target", 0.5)
    dt = obs.get("dt", 1.0)
    if not _ok(target):
        target = 0.5
    target = _clamp(float(target), 0.0, 1.0)
    if not _ok(dt) or dt <= 0.0:
        dt = 1.0
    dt = _clamp(float(dt), 0.2, 10.0)
    y_c = None
    if _ok(y_raw):
        y_c = _clamp(float(y_raw), 0.0, 1.0)
    yf_prev = state.get("yf", None)
    integ_prev = state.get("i", 0.0)
    if not _ok(yf_prev):
        yf_prev = None
    if not _ok(integ_prev):
        integ_prev = 0.0
    integ_prev = _clamp(float(integ_prev), -I_LIM, I_LIM)
    if yf_prev is None:
        if y_c is None:
            yf = target
        else:
            yf = y_c
    else:
        if y_c is None:
            yf = float(yf_prev)
        else:
            alpha = dt / (TF + dt)
            yf = float(yf_prev) + alpha * (y_c - float(yf_prev))
    yf = _clamp(float(yf), 0.0, 1.0)
    err = target - yf
    ff = (target - Y_AMB) / K_GAIN
    ff = _clamp(ff, 0.0, 0.8)
    p = KP * err
    p = _clamp(p, -P_LIM, P_LIM)
    aerr = abs(err)
    if aerr < ERR_DB:
        integ_new = integ_prev
    elif aerr > ERR_FAR:
        integ_new = integ_prev + KI_FAR * err * dt
    else:
        integ_new = integ_prev + KI * err * dt
    integ_new = _clamp(integ_new, -I_LIM, I_LIM)
    u_unsat = ff + p + integ_new
    u = _clamp(u_unsat, U_LO, U_HI)
    if u != u_unsat:
        if (u >= U_HI and err > 0.0) or (u <= U_LO and err < 0.0):
            integ_new = integ_prev
            u = _clamp(ff + p + integ_new, U_LO, U_HI)
    if not _ok(u):
        u = _clamp(ff, U_LO, U_HI)
        integ_new = integ_prev
    u = _clamp(float(u), 0.0, 1.0)
    new_state = {"yf": float(yf), "i": float(integ_new)}
    return (float(u), new_state)
