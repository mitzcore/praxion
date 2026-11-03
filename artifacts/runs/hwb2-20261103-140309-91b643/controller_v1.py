import math
def _clip(x, lo, hi):
    if x < lo:
        return lo
    if x > hi:
        return hi
    return x
def control(obs, state):
    Kp = 1.0
    Ki = 0.007
    AMB = 0.15
    GAIN = 1.32
    TAU_F = 22.0
    INT_LIM = 0.15
    U_MAX = 0.70
    try:
        y_in = float(obs.get("y", 0.5))
    except Exception:
        y_in = 0.5
    try:
        tgt_in = float(obs.get("target", 0.5))
    except Exception:
        tgt_in = 0.5
    try:
        dt_in = float(obs.get("dt", 5.0))
    except Exception:
        dt_in = 5.0
    if not math.isfinite(y_in):
        y_in = 0.5
    if not math.isfinite(tgt_in):
        tgt_in = 0.5
    if not math.isfinite(dt_in) or dt_in <= 0.0:
        dt_in = 5.0
    y_raw = _clip(y_in, 0.0, 1.0)
    target = _clip(tgt_in, 0.0, 1.0)
    dt = _clip(dt_in, 0.5, 30.0)
    if not isinstance(state, dict):
        state = {}
    yf_prev = state.get("yf", None)
    i_prev = state.get("i", 0.0)
    u_prev = state.get("u", None)
    try:
        yf_prev = float(yf_prev) if yf_prev is not None else None
    except Exception:
        yf_prev = None
    try:
        i_prev = float(i_prev)
    except Exception:
        i_prev = 0.0
    try:
        u_prev = float(u_prev) if u_prev is not None else None
    except Exception:
        u_prev = None
    if yf_prev is None or not math.isfinite(yf_prev):
        yf = y_raw
    else:
        yf_prev = _clip(yf_prev, 0.0, 1.0)
        alpha = dt / (TAU_F + dt)
        diff = abs(y_raw - yf_prev)
        if diff > 0.08:
            alpha = alpha * 0.25
        elif diff > 0.05:
            alpha = alpha * 0.5
        yf = yf_prev + alpha * (y_raw - yf_prev)
        yf = _clip(yf, 0.0, 1.0)
    if not math.isfinite(i_prev):
        i_prev = 0.0
    i_prev = _clip(i_prev, -INT_LIM, INT_LIM)
    ff = (target - AMB) / GAIN
    ff = _clip(ff, 0.0, 1.0)
    err = target - yf
    if err > 0.5:
        err = 0.5
    if err < -0.5:
        err = -0.5
    P = Kp * err
    if P > 0.35:
        P = 0.35
    if P < -0.35:
        P = -0.35
    i_prop = i_prev + Ki * err * dt
    i_prop = _clip(i_prop, -INT_LIM, INT_LIM)
    u_test = ff + P + i_prop
    integ = i_prop
    if (u_test > U_MAX and err > 0.0) or (u_test < 0.0 and err < 0.0):
        integ = i_prev
    u = ff + P + integ
    u = _clip(u, 0.0, U_MAX)
    if u_prev is not None and math.isfinite(u_prev):
        max_step = 0.10 + 0.03 * dt
        du = u - u_prev
        if du > max_step:
            u = u_prev + max_step
        elif du < -max_step:
            u = u_prev - max_step
    u = _clip(u, 0.0, 1.0)
    if not math.isfinite(u):
        u = ff
        integ = i_prev
    new_state = {"yf": float(yf), "i": float(integ), "u": float(u)}
    return (float(u), new_state)
