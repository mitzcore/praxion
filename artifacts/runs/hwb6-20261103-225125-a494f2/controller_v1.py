import math

def _clamp(v, lo, hi):
    if v < lo:
        return lo
    if v > hi:
        return hi
    return v

def control(obs, state):
    Y_AMB = 0.15
    K_EST = 1.03
    KP = 0.65
    KI = 0.008
    TF = 15.0
    I_MIN = -0.25
    I_MAX = 0.25
    U_MIN = 0.0
    U_MAX = 0.65
    INT_BAND = 0.15
    try:
        if isinstance(obs, dict):
            y_in = obs.get("y", 0.5)
            t_in = obs.get("target", 0.5)
            dt_in = obs.get("dt", 1.0)
        else:
            y_in = 0.5
            t_in = 0.5
            dt_in = 1.0
        y = float(y_in)
        target = float(t_in)
        dt = float(dt_in)
    except Exception:
        y = 0.5
        target = 0.5
        dt = 1.0
    if not math.isfinite(y):
        y = 0.5
    if not math.isfinite(target):
        target = 0.5
    if not math.isfinite(dt) or dt <= 0.0:
        dt = 1.0
    if dt < 0.05:
        dt = 0.05
    if dt > 5.0:
        dt = 5.0
    if target < 0.0:
        target = 0.0
    if target > 1.0:
        target = 1.0
    if y < 0.0:
        y = 0.0
    if y > 1.0:
        y = 1.0
    if not isinstance(state, dict):
        state = {}
    try:
        yf_prev = float(state.get("yf", y))
    except Exception:
        yf_prev = y
    try:
        integ_prev = float(state.get("integ", 0.0))
    except Exception:
        integ_prev = 0.0
    try:
        u_prev = float(state.get("u_prev", -1.0))
    except Exception:
        u_prev = -1.0
    if not math.isfinite(yf_prev):
        yf_prev = y
    if not math.isfinite(integ_prev):
        integ_prev = 0.0
    if not math.isfinite(u_prev):
        u_prev = -1.0
    yf_prev = _clamp(yf_prev, 0.0, 1.0)
    integ_prev = _clamp(integ_prev, I_MIN, I_MAX)
    alpha = dt / (TF + dt)
    if alpha < 0.0:
        alpha = 0.0
    if alpha > 1.0:
        alpha = 1.0
    yf = yf_prev + alpha * (y - yf_prev)
    if not math.isfinite(yf):
        yf = yf_prev
    yf = _clamp(yf, 0.0, 1.0)
    u_ff = (target - Y_AMB) / K_EST
    u_ff = _clamp(u_ff, U_MIN, U_MAX)
    e = target - yf
    p = KP * e
    integ = integ_prev
    if abs(e) < INT_BAND:
        cand = integ_prev + KI * e * dt
        cand = _clamp(cand, I_MIN, I_MAX)
        u_cand = u_ff + p + cand
        if u_cand > U_MAX and e > 0.0:
            integ = integ_prev
        elif u_cand < U_MIN and e < 0.0:
            integ = integ_prev
        else:
            integ = cand
    else:
        integ = integ_prev
    u_des = u_ff + p + integ
    u_des = _clamp(u_des, U_MIN, U_MAX)
    if yf > 0.80:
        u_des = U_MIN
        if integ > 0.0:
            integ = integ - 0.02 * dt
            if integ < I_MIN:
                integ = I_MIN
            if integ > I_MAX:
                integ = I_MAX
    elif yf > 0.75:
        if u_des > 0.10:
            u_des = 0.10
    if u_prev < -0.5:
        u_out = u_des
    else:
        up = _clamp(u_prev, U_MIN, U_MAX)
        max_du = 0.08 * dt
        if max_du < 0.005:
            max_du = 0.005
        if max_du > 0.30:
            max_du = 0.30
        du = u_des - up
        if du > max_du:
            du = max_du
        elif du < -max_du:
            du = -max_du
        u_out = up + du
    u_out = _clamp(u_out, U_MIN, U_MAX)
    if not math.isfinite(u_out):
        u_out = u_ff
    if u_out < 0.0:
        u_out = 0.0
    if u_out > 1.0:
        u_out = 1.0
    new_state = {"yf": float(yf), "integ": float(integ), "u_prev": float(u_out)}
    return (float(u_out), new_state)
