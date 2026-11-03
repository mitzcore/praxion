import math
def _clip(x, lo, hi):
    if x < lo:
        return lo
    if x > hi:
        return hi
    return x
def control(obs: dict, state: dict) -> tuple[float, dict]:
    AMB = 0.15
    G0 = 1.32
    Kp = 0.9
    Ki_FAR = 0.006
    Ki_NEAR = 0.022
    ERR_SPLIT = 0.12
    TAU_F = 18.0
    TAU_U = 40.0
    TAU_K = 60.0
    INT_LIM = 0.35
    U_MAX = 0.75
    K_MIN = 0.45
    K_MAX = 1.60
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
    K_prev = state.get("K", G0)
    uf_prev = state.get("uf", None)
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
    try:
        K_prev = float(K_prev)
    except Exception:
        K_prev = G0
    try:
        uf_prev = float(uf_prev) if uf_prev is not None else None
    except Exception:
        uf_prev = None
    if K_prev is None or not math.isfinite(K_prev):
        K_prev = G0
    K_prev = _clip(K_prev, K_MIN, K_MAX)
    if not math.isfinite(i_prev):
        i_prev = 0.0
    i_prev = _clip(i_prev, -INT_LIM, INT_LIM)
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
    ff_init = _clip((target - AMB) / K_prev, 0.0, 0.70)
    if uf_prev is None or not math.isfinite(uf_prev):
        if u_prev is not None and math.isfinite(u_prev):
            uf = _clip(u_prev, 0.0, 1.0)
        else:
            uf = ff_init
    else:
        uf_prev = _clip(uf_prev, 0.0, 1.0)
        if u_prev is not None and math.isfinite(u_prev):
            au = dt / (TAU_U + dt)
            uf = uf_prev + au * (_clip(u_prev, 0.0, 1.0) - uf_prev)
        else:
            uf = uf_prev
        uf = _clip(uf, 0.0, 1.0)
    Kest = K_prev
    if yf_prev is not None and math.isfinite(yf_prev):
        rate = (yf - yf_prev) / dt
        settled = False
        if u_prev is not None and math.isfinite(u_prev):
            if abs(_clip(u_prev, 0.0, 1.0) - uf) < 0.12:
                settled = True
        else:
            settled = True
        if uf > 0.10 and uf < 0.80 and yf > 0.20 and yf < 0.85 and yf > AMB + 0.03 and settled and abs(rate) < 0.0012:
            Kraw = (yf - AMB) / uf
            if math.isfinite(Kraw):
                Kraw = _clip(Kraw, 0.40, 1.65)
                beta = dt / (TAU_K + dt)
                Kest = K_prev + beta * (Kraw - K_prev)
                Kest = _clip(Kest, K_MIN, K_MAX)
    ff = (target - AMB) / Kest
    if not math.isfinite(ff):
        ff = ff_init
    ff = _clip(ff, 0.0, 0.70)
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
    Ki_eff = Ki_NEAR if abs(err) <= ERR_SPLIT else Ki_FAR
    i_prop = i_prev + Ki_eff * err * dt
    i_prop = _clip(i_prop, -INT_LIM, INT_LIM)
    u_test = ff + P + i_prop
    integ = i_prop
    if (u_test > U_MAX and err > 0.0) or (u_test < 0.0 and err < 0.0):
        integ = i_prev
    u = ff + P + integ
    u = _clip(u, 0.0, U_MAX)
    if u_prev is not None and math.isfinite(u_prev):
        max_step = 0.12 + 0.04 * dt
        du = u - u_prev
        if du > max_step:
            u = u_prev + max_step
        elif du < -max_step:
            u = u_prev - max_step
    u = _clip(u, 0.0, 1.0)
    if not math.isfinite(u):
        u = ff
        integ = i_prev
    new_state = {"yf": float(yf), "i": float(integ), "u": float(u), "K": float(Kest), "uf": float(uf)}
    return (float(u), new_state)
