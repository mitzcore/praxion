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
    K_INIT = 1.02
    K_LO = 0.32
    K_HI = 1.35
    KP = 0.70
    KI_NEAR = 0.022
    KI_FAR = 0.065
    KD = 15.0
    TD = 10.0
    D_LIM = 0.25
    TF = 5.0
    TS = 30.0
    I_LIM = 0.90
    P_LIM = 0.50
    ERR_FAR = 0.07
    ERR_DB = 0.003
    U_LO = 0.0
    U_HI = 1.0
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
    if not _ok(yf_prev):
        yf_prev = None
    integ_prev = state.get("i", 0.0)
    if not _ok(integ_prev):
        integ_prev = 0.0
    integ_prev = _clamp(float(integ_prev), -I_LIM, I_LIM)
    k_hat = state.get("k", K_INIT)
    if not _ok(k_hat):
        k_hat = K_INIT
    k_hat = _clamp(float(k_hat), K_LO, K_HI)
    y_s = state.get("ys", None)
    u_s = state.get("us", None)
    u_prev = state.get("up", None)
    df_prev = state.get("df", 0.0)
    if not _ok(df_prev):
        df_prev = 0.0
    low = state.get("low", 0.0)
    if not _ok(low):
        low = 0.0
    t_run = state.get("t", 0.0)
    if not _ok(t_run):
        t_run = 0.0
    t_run = float(t_run) + float(dt)
    if yf_prev is None:
        yf = float(y_c) if y_c is not None else float(target)
        yf_old = float(yf)
    else:
        yf_old = float(yf_prev)
        if y_c is None:
            yf = float(yf_prev)
        else:
            alpha = float(dt) / (TF + float(dt))
            yf = float(yf_prev) + alpha * (float(y_c) - float(yf_prev))
    yf = _clamp(float(yf), 0.0, 1.0)
    if y_s is None or not _ok(y_s):
        y_s = float(yf)
    else:
        y_s = float(y_s)
    if u_s is None or not _ok(u_s):
        u_s = float(u_prev) if _ok(u_prev) else 0.39
    else:
        u_s = float(u_s)
    if not _ok(u_prev):
        up_f = float(u_s)
    else:
        up_f = _clamp(float(u_prev), 0.0, 1.0)
    al_s = float(dt) / (TS + float(dt))
    y_s = y_s + al_s * (float(yf) - y_s)
    u_s = u_s + al_s * (up_f - u_s)
    y_s = _clamp(float(y_s), 0.0, 1.0)
    u_s = _clamp(float(u_s), 0.0, 1.0)
    steady = (abs(float(yf) - y_s) < 0.022 and abs(up_f - u_s) < 0.10)
    if steady:
        tau_k = 40.0
    else:
        tau_k = 150.0
    if t_run > 120.0 and (target - float(yf)) > 0.06 and u_s > 0.55:
        tau_k = 22.0
    w = float(dt) / tau_k
    if w < 0.0:
        w = 0.0
    if w > 0.08:
        w = 0.08
    if u_s > 0.15 and y_s > 0.11:
        denom = u_s if u_s > 0.05 else 0.05
        k_imp = (y_s - Y_AMB) / denom
        if _ok(k_imp):
            k_imp = _clamp(float(k_imp), 0.30, 1.45)
            k_hat = float(k_hat) + w * (k_imp - float(k_hat))
            k_hat = _clamp(float(k_hat), K_LO, K_HI)
    err_for_low = float(target) - float(yf)
    if t_run > 120.0 and err_for_low > 0.07 and u_s > 0.55 and float(yf) < 0.45:
        low = float(low) + float(dt)
    else:
        low = float(low) - float(dt)
        if low < 0.0:
            low = 0.0
    if low > 35.0:
        k_hat = _clamp(float(k_hat) - 0.08, K_LO, K_HI)
        low = 20.0
    if k_hat > 0.1:
        ff = (float(target) - Y_AMB) / float(k_hat)
    else:
        ff = (float(target) - Y_AMB) / 0.4
    ff = _clamp(float(ff), 0.0, 1.0)
    err = float(target) - float(yf)
    p = KP * err
    p = _clamp(p, -P_LIM, P_LIM)
    aerr = abs(err)
    if aerr < ERR_DB:
        integ_new = integ_prev
    elif aerr > ERR_FAR:
        integ_new = integ_prev + KI_FAR * err * float(dt)
    else:
        integ_new = integ_prev + KI_NEAR * err * float(dt)
    integ_new = _clamp(float(integ_new), -I_LIM, I_LIM)
    raw_d = 0.0
    if yf_prev is not None:
        raw_d = (float(yf) - float(yf_old)) / float(dt)
        if not _ok(raw_d):
            raw_d = 0.0
    df_new = float(df_prev) + (float(dt) / (TD + float(dt))) * (float(raw_d) - float(df_prev))
    if not _ok(df_new):
        df_new = 0.0
    d_term = -KD * float(df_new)
    d_term = _clamp(float(d_term), -D_LIM, D_LIM)
    u_unsat = float(ff) + float(p) + float(integ_new) + float(d_term)
    u = _clamp(u_unsat, U_LO, U_HI)
    if u != u_unsat:
        if (u >= U_HI and err > 0.0) or (u <= U_LO and err < 0.0):
            integ_new = float(integ_prev)
            u = _clamp(float(ff) + float(p) + float(integ_new) + float(d_term), U_LO, U_HI)
    if float(yf) > 0.82:
        u = min(float(u), 0.0)
    elif float(yf) > 0.78:
        u = min(float(u), 0.20)
    if not _ok(u):
        u = _clamp(float(ff), U_LO, U_HI)
        integ_new = float(integ_prev)
        df_new = float(df_prev)
    u = _clamp(float(u), 0.0, 1.0)
    new_state = {"yf": float(yf), "i": float(integ_new), "k": float(k_hat), "ys": float(y_s), "us": float(u_s), "up": float(u), "df": float(df_new), "low": float(low), "t": float(t_run)}
    return (float(u), new_state)
