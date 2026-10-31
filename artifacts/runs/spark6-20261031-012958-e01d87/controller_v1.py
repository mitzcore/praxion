import math
def control(obs, state):
    def _clamp(v, lo, hi):
        if not math.isfinite(v):
            return (lo + hi) * 0.5
        if v < lo:
            return lo
        if v > hi:
            return hi
        return v
    try:
        y_in = float(obs.get("y", 0.6))
    except Exception:
        y_in = 0.6
    try:
        t_in = float(obs.get("target", 0.6))
    except Exception:
        t_in = 0.6
    try:
        dt_in = float(obs.get("dt", 0.1))
    except Exception:
        dt_in = 0.1
    if not math.isfinite(y_in):
        y_in = 0.6
    if not math.isfinite(t_in):
        t_in = 0.6
    if not math.isfinite(dt_in) or dt_in <= 0.0:
        dt_in = 0.1
    y_raw = _clamp(y_in, 0.0, 1.0)
    target = _clamp(t_in, 0.0, 1.0)
    dt = _clamp(dt_in, 0.02, 1.0)
    FF = 0.75
    KP = 0.28
    KI = 0.055
    KD = 0.8
    TAU_F = 1.2
    TAU_D = 0.8
    I_LIM = 0.08
    INT_LIM = 1.5
    D_LIM = 0.12
    try:
        yf = float(state.get("yf", y_raw))
    except Exception:
        yf = y_raw
    try:
        integ = float(state.get("integ", 0.0))
    except Exception:
        integ = 0.0
    try:
        dfilt = float(state.get("dfilt", 0.0))
    except Exception:
        dfilt = 0.0
    try:
        prev_u = float(state.get("prev_u", 0.6))
    except Exception:
        prev_u = 0.6
    if not math.isfinite(yf):
        yf = y_raw
    if not math.isfinite(integ):
        integ = 0.0
    if not math.isfinite(dfilt):
        dfilt = 0.0
    if not math.isfinite(prev_u):
        prev_u = 0.6
    yf = _clamp(yf, 0.0, 1.0)
    integ = _clamp(integ, -INT_LIM, INT_LIM)
    dfilt = _clamp(dfilt, -0.5, 0.5)
    prev_u = _clamp(prev_u, 0.0, 1.0)
    is_init = ("yf" not in state) or ("prev_u" not in state)
    if is_init:
        yf = y_raw
        dfilt = 0.0
        integ = 0.0
        prev_u = 0.6
    prev_yf = yf
    alpha = dt / (TAU_F + dt)
    yf = yf + alpha * (y_raw - yf)
    yf = _clamp(yf, 0.0, 1.0)
    raw_rate = (yf - prev_yf) / dt
    if not math.isfinite(raw_rate):
        raw_rate = 0.0
    raw_rate = _clamp(raw_rate, -0.5, 0.5)
    beta = dt / (TAU_D + dt)
    dfilt = dfilt + beta * (raw_rate - dfilt)
    dfilt = _clamp(dfilt, -0.5, 0.5)
    err = target - yf
    err = _clamp(err, -1.0, 1.0)
    P = KP * err
    P = _clamp(P, -0.2, 0.2)
    D = -KD * dfilt
    D = _clamp(D, -D_LIM, D_LIM)
    allow_int = True
    if yf < 0.45:
        allow_int = False
    if abs(err) > 0.30:
        allow_int = False
    if yf > 0.85:
        allow_int = False
    integ_cand = integ
    if allow_int:
        integ_cand = integ + err * dt
        integ_cand = _clamp(integ_cand, -INT_LIM, INT_LIM)
    I_cand = _clamp(KI * integ_cand, -I_LIM, I_LIM)
    u_tmp = FF + P + I_cand + D
    if yf >= 0.80:
        cap = 0.35
    elif yf > 0.65:
        cap = 0.78 - 2.0 * (yf - 0.65)
        cap = _clamp(cap, 0.30, 0.78)
    else:
        cap = 0.84 if yf < 0.50 else 0.82
    if y_raw > 0.82:
        if cap > 0.30:
            cap = 0.30
    max_u = cap
    if max_u > 0.84:
        max_u = 0.84
    if max_u < 0.0:
        max_u = 0.0
    u_des = u_tmp
    if u_des > max_u:
        u_des = max_u
    if u_des < 0.0:
        u_des = 0.0
    saturated_high = (u_tmp > max_u + 1e-9)
    saturated_low = (u_tmp < 0.0 - 1e-9)
    if (saturated_high and err > 0.0) or (saturated_low and err < 0.0):
        integ_next = integ
        I_now = _clamp(KI * integ_next, -I_LIM, I_LIM)
        u_tmp2 = FF + P + I_now + D
        u_des = u_tmp2
        if u_des > max_u:
            u_des = max_u
        if u_des < 0.0:
            u_des = 0.0
    else:
        integ_next = integ_cand
    du = u_des - prev_u
    max_up = 0.12 * dt + 0.005
    max_dn = 1.5 * dt + 0.02
    if du > max_up:
        du = max_up
    elif du < -max_dn:
        du = -max_dn
    if yf >= 0.80 and u_des < prev_u:
        du = u_des - prev_u
        fast_dn = 2.5 * dt + 0.05
        if du < -fast_dn:
            du = -fast_dn
    u = prev_u + du
    u = _clamp(u, 0.0, 1.0)
    if not math.isfinite(u):
        u = 0.6
    new_state = {"yf": float(yf), "integ": float(integ_next), "dfilt": float(dfilt), "prev_u": float(u)}
    return (float(u), new_state)
