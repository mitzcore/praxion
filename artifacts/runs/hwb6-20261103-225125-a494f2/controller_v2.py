import math

def _clamp(v, lo, hi):
    if v < lo:
        return lo
    if v > hi:
        return hi
    return v

def control(obs, state):
    Y_AMB = 0.14
    K_EST = 1.10
    KP = 0.90
    KI = 0.018
    KD = 28.0
    KA = 0.005
    TF_F = 8.0
    TF_S = 35.0
    TF_D = 18.0
    U_MIN = 0.0
    U_MAX = 0.68
    I_MIN = -0.30
    I_MAX = 0.30
    FF_MIN = 0.10
    FF_MAX = 0.65
    D_LIM = 0.12
    INT_GATE = 0.25
    FF_GATE = 0.10
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
    y_valid = math.isfinite(y)
    if not y_valid:
        y = 0.5
    if not math.isfinite(target):
        target = 0.5
    if not math.isfinite(dt) or dt <= 0.0:
        dt = 1.0
    if dt < 0.05:
        dt = 0.05
    if dt > 10.0:
        dt = 10.0
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
        ys_prev = float(state.get("ys", y))
    except Exception:
        ys_prev = y
    try:
        df_prev = float(state.get("df", 0.0))
    except Exception:
        df_prev = 0.0
    try:
        integ_prev = float(state.get("integ", 0.0))
    except Exception:
        integ_prev = 0.0
    try:
        uff_prev = float(state.get("uff", -99.0))
    except Exception:
        uff_prev = -99.0
    try:
        u_prev = float(state.get("u_prev", -1.0))
    except Exception:
        u_prev = -1.0
    if not math.isfinite(yf_prev):
        yf_prev = y
    if not math.isfinite(ys_prev):
        ys_prev = y
    if not math.isfinite(df_prev):
        df_prev = 0.0
    if not math.isfinite(integ_prev):
        integ_prev = 0.0
    if not math.isfinite(uff_prev):
        uff_prev = -99.0
    if not math.isfinite(u_prev):
        u_prev = -1.0
    yf_prev = _clamp(yf_prev, 0.0, 1.0)
    ys_prev = _clamp(ys_prev, 0.0, 1.0)
    integ_prev = _clamp(integ_prev, I_MIN, I_MAX)
    ff0 = (target - Y_AMB) / K_EST
    ff0 = _clamp(ff0, FF_MIN, FF_MAX)
    if uff_prev < -50.0:
        uff_prev = ff0
    uff_prev = _clamp(uff_prev, FF_MIN, FF_MAX)
    if not y_valid:
        yf = yf_prev
        ys = ys_prev
        df = df_prev
    else:
        af = dt / (TF_F + dt)
        if af < 0.0:
            af = 0.0
        if af > 1.0:
            af = 1.0
        yf = yf_prev + af * (y - yf_prev)
        if not math.isfinite(yf):
            yf = yf_prev
        yf = _clamp(yf, 0.0, 1.0)
        a_s = dt / (TF_S + dt)
        if a_s < 0.0:
            a_s = 0.0
        if a_s > 1.0:
            a_s = 1.0
        ys = ys_prev + a_s * (y - ys_prev)
        if not math.isfinite(ys):
            ys = ys_prev
        ys = _clamp(ys, 0.0, 1.0)
        raw = (yf - yf_prev) / dt
        if not math.isfinite(raw):
            raw = 0.0
        if raw > 0.05:
            raw = 0.05
        if raw < -0.05:
            raw = -0.05
        ad = dt / (TF_D + dt)
        if ad < 0.0:
            ad = 0.0
        if ad > 1.0:
            ad = 1.0
        df = df_prev + ad * (raw - df_prev)
        if not math.isfinite(df):
            df = df_prev
        if df > 0.02:
            df = 0.02
        if df < -0.02:
            df = -0.02
    e = target - yf
    e_s = target - ys
    d_term = -KD * df
    d_term = _clamp(d_term, -D_LIM, D_LIM)
    p_term = KP * e
    integ_cand = integ_prev
    if abs(e) < INT_GATE:
        integ_cand = integ_prev + KI * e * dt
        integ_cand = _clamp(integ_cand, I_MIN, I_MAX)
    uff_cand = uff_prev
    if abs(e_s) < FF_GATE:
        uff_cand = uff_prev + KA * e_s * dt
        uff_cand = _clamp(uff_cand, FF_MIN, FF_MAX)
    u_des_cand = uff_cand + p_term + integ_cand + d_term
    u_des_cand = _clamp(u_des_cand, U_MIN, U_MAX)
    # anti-windup: freeze adaptation if saturated and pushing further
    if (u_des_cand >= U_MAX - 1e-9 and e > 0.0) or (u_des_cand <= U_MIN + 1e-9 and e < 0.0):
        integ = integ_prev
        uff = uff_prev
        u_des = uff + p_term + integ + d_term
        u_des = _clamp(u_des, U_MIN, U_MAX)
    else:
        integ = integ_cand
        uff = uff_cand
        u_des = u_des_cand
    if yf > 0.80:
        u_des = U_MIN
        if integ > 0.0:
            integ = integ - 0.02 * dt
            integ = _clamp(integ, I_MIN, I_MAX)
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
        u_out = ff0
    if u_out < 0.0:
        u_out = 0.0
    if u_out > 1.0:
        u_out = 1.0
    new_state = {"yf": float(yf), "ys": float(ys), "df": float(df), "integ": float(integ), "uff": float(uff), "u_prev": float(u_out)}
    return (float(u_out), new_state)
