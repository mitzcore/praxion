import math
def control(obs, state):
    def _clamp(v, lo, hi):
        if not math.isfinite(v):
            return (lo+hi)*0.5
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
    FF_INIT = 0.66
    FF_MIN = 0.35
    FF_MAX = 0.82
    KP = 0.55
    P_LIM = 0.16
    KI = 0.06
    I_LIM = 0.30
    INT_LIM = 5.0
    KD = 0.70
    D_LIM = 0.12
    TAU_F = 1.2
    TAU_D = 0.9
    ABS_MAX = 0.86
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
        prev_u = float(state.get("prev_u", FF_INIT))
    except Exception:
        prev_u = FF_INIT
    try:
        ff = float(state.get("ff", FF_INIT))
    except Exception:
        ff = FF_INIT
    if not math.isfinite(yf):
        yf = y_raw
    if not math.isfinite(integ):
        integ = 0.0
    if not math.isfinite(dfilt):
        dfilt = 0.0
    if not math.isfinite(prev_u):
        prev_u = FF_INIT
    if not math.isfinite(ff):
        ff = FF_INIT
    yf = _clamp(yf, 0.0, 1.0)
    integ = _clamp(integ, -INT_LIM, INT_LIM)
    dfilt = _clamp(dfilt, -0.5, 0.5)
    prev_u = _clamp(prev_u, 0.0, 1.0)
    ff = _clamp(ff, FF_MIN, FF_MAX)
    is_init = ("yf" not in state) or ("prev_u" not in state) or ("ff" not in state)
    if is_init:
        yf = y_raw
        dfilt = 0.0
        integ = 0.0
        ff = FF_INIT
        prev_u = _clamp(FF_INIT, 0.0, 1.0)
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
    P = _clamp(P, -P_LIM, P_LIM)
    D = -KD * dfilt
    D = _clamp(D, -D_LIM, D_LIM)
    if yf >= 0.82:
        cap = 0.22
    elif yf > 0.65:
        cap = ff + 0.04 - 1.8 * (yf - 0.65)
        cap = _clamp(cap, 0.22, ABS_MAX)
    else:
        cap = ABS_MAX
    if y_raw > 0.84 and cap > 0.25:
        cap = 0.25
    if cap > ABS_MAX:
        cap = ABS_MAX
    if cap < 0.0:
        cap = 0.0
    integ_cand = integ + err * dt
    integ_cand = _clamp(integ_cand, -INT_LIM, INT_LIM)
    I_cand = _clamp(KI * integ_cand, -I_LIM, I_LIM)
    u_tmp = ff + P + I_cand + D
    sat_hi = (u_tmp > cap + 1e-9)
    sat_lo = (u_tmp < 0.0 - 1e-9)
    allow_integ = True
    if (sat_hi and err > 0.0) or (sat_lo and err < 0.0):
        allow_integ = False
    if abs(err) > 0.35:
        pass
    if yf >= 0.82 and err < 0.0:
        allow_integ = True
    if allow_integ:
        integ_next = integ_cand
    else:
        integ_next = integ
    I_now = _clamp(KI * integ_next, -I_LIM, I_LIM)
    u_tmp2 = ff + P + I_now + D
    u_des = u_tmp2
    if u_des > cap:
        u_des = cap
    if u_des < 0.0:
        u_des = 0.0
    du = u_des - prev_u
    max_up = 0.45 * dt + 0.015
    max_dn = 0.90 * dt + 0.025
    if du > max_up:
        du = max_up
    elif du < -max_dn:
        du = -max_dn
    if yf >= 0.78 and u_des < prev_u:
        fast_dn = 2.0 * dt + 0.05
        dd = u_des - prev_u
        if dd < -fast_dn:
            dd = -fast_dn
        du = dd
    u = prev_u + du
    u = _clamp(u, 0.0, 1.0)
    if not math.isfinite(u):
        u = ff
    ff_next = ff
    try:
        if abs(err) < 0.07 and abs(dfilt) < 0.025 and yf > 0.40 and yf < 0.78:
            ff_next = ff + (u - ff) * dt / 20.0
            ff_next = _clamp(ff_next, FF_MIN, FF_MAX)
    except Exception:
        ff_next = ff
    new_state = {"yf": float(yf), "integ": float(integ_next), "dfilt": float(dfilt), "prev_u": float(u), "ff": float(ff_next)}
    return (float(u), new_state)
