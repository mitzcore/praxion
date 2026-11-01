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
    Y_AMB = 0.085
    K_INIT = 1.05
    K_LO = 0.30
    K_HI = 1.35
    KP = 0.9
    KI_NEAR = 0.018
    KI_FAR = 0.045
    TF = 6.0
    TS = 32.0
    I_LIM = 0.75
    P_LIM = 0.65
    U_LO = 0.0
    U_HI = 1.0
    ERR_FAR = 0.08
    ERR_DB = 0.002
    if state is None:
        state = {}
    y_raw = obs.get("y", 0.5)
    target = obs.get("target", 0.5)
    dt = obs.get("dt", 1.0)
    elapsed = obs.get("elapsed_s", None)
    if not _ok(target):
        target = 0.5
    target = _clamp(float(target), 0.0, 1.0)
    if not _ok(dt) or dt <= 0.0:
        dt = 1.0
    dt = _clamp(float(dt), 0.2, 10.0)
    if not _ok(elapsed):
        elapsed = None
    else:
        elapsed = float(elapsed)
    y_c = None
    if _ok(y_raw):
        y_c = _clamp(float(y_raw), 0.0, 1.0)
    yf_prev = state.get("yf", None)
    integ_prev = state.get("i", 0.0)
    k_hat = state.get("k", K_INIT)
    y_s = state.get("ys", None)
    u_s = state.get("us", None)
    u_prev = state.get("up", None)
    if not _ok(integ_prev):
        integ_prev = 0.0
    integ_prev = _clamp(float(integ_prev), -I_LIM, I_LIM)
    if not _ok(k_hat):
        k_hat = K_INIT
    k_hat = _clamp(float(k_hat), K_LO, K_HI)
    if not _ok(yf_prev):
        yf_prev = None
    if yf_prev is None:
        yf = target if y_c is None else float(y_c)
    else:
        if y_c is None:
            yf = float(yf_prev)
        else:
            alpha = dt / (TF + dt)
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
        u_prev_f = float(u_s)
    else:
        u_prev_f = _clamp(float(u_prev), 0.0, 1.0)
    al_s = dt / (TS + dt)
    y_s = y_s + al_s * (float(yf) - y_s)
    u_s = u_s + al_s * (u_prev_f - u_s)
    y_s = _clamp(float(y_s), 0.0, 1.0)
    u_s = _clamp(float(u_s), 0.0, 1.0)
    if u_s > 0.15 and y_s > 0.11:
        steady = (abs(float(yf) - y_s) < 0.025 and abs(u_prev_f - u_s) < 0.12)
        tau_k = 55.0 if steady else 220.0
        w = dt / tau_k
        if w < 0.0:
            w = 0.0
        if w > 0.05:
            w = 0.05
        denom = u_s if u_s > 0.05 else 0.05
        k_imp = (y_s - Y_AMB) / denom
        if _ok(k_imp):
            k_imp = _clamp(float(k_imp), 0.28, 1.45)
            k_hat = float(k_hat) + w * (k_imp - float(k_hat))
            k_hat = _clamp(float(k_hat), K_LO, K_HI)
    if k_hat > 0.1:
        ff = (target - Y_AMB) / k_hat
    else:
        ff = (target - Y_AMB) / 0.4
    ff = _clamp(float(ff), 0.0, 1.0)
    err = target - float(yf)
    p = KP * err
    p = _clamp(p, -P_LIM, P_LIM)
    aerr = abs(err)
    if aerr < ERR_DB:
        integ_new = integ_prev
    elif aerr > ERR_FAR:
        integ_new = integ_prev + KI_FAR * err * dt
    else:
        integ_new = integ_prev + KI_NEAR * err * dt
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
    new_state = {"yf": float(yf), "i": float(integ_new), "k": float(k_hat), "ys": float(y_s), "us": float(u_s), "up": float(u)}
    return (float(u), new_state)
