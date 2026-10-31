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
    y_in = obs.get("y", 0.6)
    t_in = obs.get("target", 0.6)
    dt_in = obs.get("dt", 0.2)
    try:
        y_raw0 = float(y_in)
    except:
        y_raw0 = 0.6
    try:
        t_raw0 = float(t_in)
    except:
        t_raw0 = 0.6
    try:
        dt_raw0 = float(dt_in)
    except:
        dt_raw0 = 0.2
    if not math.isfinite(y_raw0):
        y_raw0 = 0.6
    if not math.isfinite(t_raw0):
        t_raw0 = 0.6
    if not math.isfinite(dt_raw0) or dt_raw0 <= 0.0:
        dt_raw0 = 0.2
    y_raw = _clamp(y_raw0, 0.0, 1.0)
    target = _clamp(t_raw0, 0.0, 1.0)
    dt = _clamp(dt_raw0, 0.02, 1.0)
    if state is None:
        state = {}
    KP = 0.85
    TI = 14.0
    KI = KP / TI
    TAUF = 1.2
    FF0 = 0.48
    I_AUTH = 0.22
    UMAX = 0.80
    UMIN = 0.0
    SLEW_UP = 0.6
    SLEW_DN = 1.2
    I_SUM_MAX = I_AUTH / KI
    ff = FF0 + (target - 0.6) * 0.9
    ff = _clamp(ff, 0.05, 0.80)
    first = False
    try:
        yf_prev = float(state.get("yf", y_raw))
        integ_prev = float(state.get("i", 0.0))
        pu_prev = float(state.get("pu", ff))
    except:
        yf_prev = y_raw
        integ_prev = 0.0
        pu_prev = ff
        first = True
    if not math.isfinite(yf_prev):
        yf_prev = y_raw
        first = True
    if not math.isfinite(integ_prev):
        integ_prev = 0.0
    if not math.isfinite(pu_prev):
        pu_prev = ff
    if "yf" not in state or "i" not in state or "pu" not in state:
        first = True
        yf_prev = y_raw
        integ_prev = 0.0
        pu_prev = ff
    yf_prev = _clamp(yf_prev, 0.0, 1.0)
    integ_prev = _clamp(integ_prev, -I_SUM_MAX, I_SUM_MAX)
    pu_prev = _clamp(pu_prev, 0.0, 1.0)
    alpha = dt / (TAUF + dt)
    if first:
        yf = y_raw
    else:
        yf = (1.0 - alpha) * yf_prev + alpha * y_raw
    yf = _clamp(yf, 0.0, 1.0)
    e = target - yf
    enable = (abs(e) < 0.18) and (yf < 0.78) and (y_raw < 0.85)
    if enable:
        integ_new = integ_prev + e * dt
        integ_new = _clamp(integ_new, -I_SUM_MAX, I_SUM_MAX)
    else:
        integ_new = integ_prev
    P = KP * e
    Iterm = KI * integ_new
    Iterm = _clamp(Iterm, -I_AUTH, I_AUTH)
    u_tmp = ff + P + Iterm
    if (u_tmp > UMAX and e > 0.0) or (u_tmp < UMIN and e < 0.0):
        integ_new = integ_prev
        Iterm = _clamp(KI * integ_new, -I_AUTH, I_AUTH)
        u_tmp = ff + P + Iterm
    if u_tmp > UMAX:
        u_tmp = UMAX
    if u_tmp < UMIN:
        u_tmp = UMIN
    safety = False
    if y_raw >= 0.85 or yf >= 0.84:
        u_tmp = 0.0
        safety = True
        if integ_new > 0.0:
            integ_new = 0.0
    elif yf > 0.78:
        if u_tmp > 0.15:
            u_tmp = 0.15
        safety = True
        if integ_new > integ_prev and e > 0.0:
            integ_new = integ_prev
    u_out = u_tmp
    if not safety and not first:
        du = u_out - pu_prev
        up_lim = SLEW_UP * dt
        dn_lim = SLEW_DN * dt
        if du > up_lim:
            u_out = pu_prev + up_lim
        elif du < -dn_lim:
            u_out = pu_prev - dn_lim
    if first:
        if safety:
            pass
        else:
            du0 = u_out - ff
            up0 = SLEW_UP * dt
            dn0 = SLEW_DN * dt
            if du0 > up0:
                u_out = ff + up0
            elif du0 < -dn0:
                u_out = ff - dn0
    u_out = _clamp(u_out, 0.0, 1.0)
    if not math.isfinite(u_out):
        u_out = _clamp(pu_prev, 0.0, 1.0)
    new_state = {"yf": float(yf), "i": float(integ_new), "pu": float(u_out)}
    return (float(u_out), new_state)
