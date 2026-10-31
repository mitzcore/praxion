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
    KP = 0.32
    P_LIM = 0.20
    KI = 0.08
    I_LIM = 0.28
    INT_LIM = 3.5
    TAU_F = 1.0
    TAU_D = 1.0
    TPRED = 3.2
    FF_INIT = 0.66
    FF_MIN = 0.30
    FF_MAX = 0.85
    ABS_MAX = 0.86
    try:
        yf = float(state.get("yf", y_raw))
    except Exception:
        yf = y_raw
    try:
        dfilt = float(state.get("dfilt", 0.0))
    except Exception:
        dfilt = 0.0
    try:
        integ = float(state.get("integ", 0.0))
    except Exception:
        integ = 0.0
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
    if not math.isfinite(dfilt):
        dfilt = 0.0
    if not math.isfinite(integ):
        integ = 0.0
    if not math.isfinite(prev_u):
        prev_u = FF_INIT
    if not math.isfinite(ff):
        ff = FF_INIT
    yf = _clamp(yf, 0.0, 1.0)
    dfilt = _clamp(dfilt, -0.5, 0.5)
    integ = _clamp(integ, -INT_LIM, INT_LIM)
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
    y_pred = yf + TPRED * dfilt
    y_pred = _clamp(y_pred, 0.0, 1.0)
    err_f = _clamp(target - yf, -1.0, 1.0)
    err_p = _clamp(target - y_pred, -1.0, 1.0)
    P = KP * err_p
    P = _clamp(P, -P_LIM, P_LIM)
    brake = 0.0
    if yf > 0.50 and dfilt > 0.005:
        w = (yf - 0.50) / 0.10
        if w < 0.0:
            w = 0.0
        if w > 1.0:
            w = 1.0
        brake = 2.0 * dfilt * w
        brake = _clamp(brake, 0.0, 0.25)
    if abs(err_f) > 0.25:
        integ_rate = err_f * 0.20
    elif abs(err_f) > 0.15:
        integ_rate = err_f * 0.60
    else:
        integ_rate = err_f
    integ_cand = integ + integ_rate * dt
    integ_cand = _clamp(integ_cand, -INT_LIM, INT_LIM)
    I_cand = _clamp(KI * integ_cand, -I_LIM, I_LIM)
    u_tmp = ff + P + I_cand - brake
    cap = ABS_MAX
    if yf >= 0.70:
        c = 0.86 - 2.2 * (yf - 0.70)
        if c < 0.35:
            c = 0.35
        if c < cap:
            cap = c
    if y_pred >= 0.72 and cap > 0.60:
        cap = 0.60
    if y_raw > 0.84 and cap > 0.25:
        cap = 0.25
    u_sat = u_tmp
    if u_sat > cap:
        u_sat = cap
    if u_sat < 0.0:
        u_sat = 0.0
    sat_hi = (u_tmp > cap + 1e-9)
    sat_lo = (u_tmp < 0.0 - 1e-9)
    allow = True
    if (sat_hi and err_f > 0.0) or (sat_lo and err_f < 0.0):
        allow = False
    if allow:
        integ_next = integ_cand
    else:
        integ_next = integ
    I_now = _clamp(KI * integ_next, -I_LIM, I_LIM)
    u_des = ff + P + I_now - brake
    if u_des > cap:
        u_des = cap
    if u_des < 0.0:
        u_des = 0.0
    du = u_des - prev_u
    max_up = 0.25 * dt + 0.008
    max_dn = 0.50 * dt + 0.015
    if du > max_up:
        du = max_up
    elif du < -max_dn:
        du = -max_dn
    if yf >= 0.76 and u_des < prev_u:
        fast_dn = 1.2 * dt + 0.03
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
        settled = (abs(err_f) < 0.10 and abs(dfilt) < 0.025 and yf > 0.28 and yf < 0.80)
        tight = (abs(err_f) < 0.05 and yf >= 0.30 and yf <= 0.80)
        if tight:
            ff_next = ff + (u - ff) * dt / 8.0
            ff_next = _clamp(ff_next, FF_MIN, FF_MAX)
        elif settled:
            ff_next = ff + (u - ff) * dt / 12.0
            ff_next = _clamp(ff_next, FF_MIN, FF_MAX)
    except Exception:
        ff_next = ff
    new_state = {"yf": float(yf), "integ": float(integ_next), "dfilt": float(dfilt), "prev_u": float(u), "ff": float(ff_next)}
    return (float(u), new_state)
