import math

def _ff_for_target(t):
    if not math.isfinite(t):
        t = 0.5
    if t < 0.0:
        t = 0.0
    if t > 1.0:
        t = 1.0
    if t <= 0.17:
        return 0.0
    if t <= 0.508:
        return (t - 0.17) / 1.352
    if t <= 0.547:
        return 0.25 + (t - 0.508) / 0.78
    return 0.3 + (t - 0.547) / 0.78

def control(obs, state):
    Kp = 0.85
    Ki = 0.009
    Tf = 14.0
    UMAX = 0.65
    UMIN = 0.0
    RLIM = 0.05
    I_AUTH = 0.15
    try:
        y_raw = obs.get("y", 0.5)
        tgt = obs.get("target", 0.5)
        dt_in = obs.get("dt", 1.0)
    except Exception:
        return 0.24, {"yf": 0.5, "I": 0.0, "u": 0.24}
    if not isinstance(state, dict):
        state = {}
    try:
        y = float(y_raw)
    except Exception:
        y = float(state.get("yf", 0.5))
    try:
        target = float(tgt)
    except Exception:
        target = 0.5
    try:
        dt = float(dt_in)
    except Exception:
        dt = 1.0
    if not math.isfinite(y):
        y = float(state.get("yf", 0.5))
        if not math.isfinite(y):
            y = 0.5
    if not math.isfinite(target):
        target = 0.5
    if target < 0.0:
        target = 0.0
    if target > 1.0:
        target = 1.0
    if not math.isfinite(dt) or dt < 0.05:
        dt = 0.05
    if dt > 10.0:
        dt = 10.0
    if y < -0.2:
        y = -0.2
    if y > 1.2:
        y = 1.2
    ff = _ff_for_target(target)
    if ff < UMIN:
        ff = UMIN
    if ff > UMAX:
        ff = UMAX
    first = ("yf" not in state) or ("u" not in state)
    try:
        yf_prev = float(state.get("yf", y))
    except Exception:
        yf_prev = y
    if not math.isfinite(yf_prev):
        yf_prev = y
    if yf_prev < 0.0:
        yf_prev = 0.0
    if yf_prev > 1.0:
        yf_prev = 1.0
    try:
        I_old = float(state.get("I", 0.0))
    except Exception:
        I_old = 0.0
    if not math.isfinite(I_old):
        I_old = 0.0
    try:
        u_prev = float(state.get("u", ff))
    except Exception:
        u_prev = ff
    if not math.isfinite(u_prev):
        u_prev = ff
    if u_prev < UMIN:
        u_prev = UMIN
    if u_prev > UMAX:
        u_prev = UMAX
    alpha = dt / (Tf + dt)
    lim = 0.035 + 0.004 * dt
    innov = y - yf_prev
    if innov > lim:
        innov = lim
    elif innov < -lim:
        innov = -lim
    yf = yf_prev + alpha * innov
    if not math.isfinite(yf):
        yf = yf_prev
    if yf < 0.0:
        yf = 0.0
    if yf > 1.0:
        yf = 1.0
    e = target - yf
    I_lim = I_AUTH / Ki
    I_cand = I_old + e * dt
    if I_cand > I_lim:
        I_cand = I_lim
    elif I_cand < -I_lim:
        I_cand = -I_lim
    P = Kp * e
    u_raw_cand = ff + P + Ki * I_cand
    I_new = I_cand
    u_raw = u_raw_cand
    if abs(e) > 0.15:
        I_new = I_old
        u_raw = ff + P + Ki * I_old
    else:
        if (u_raw_cand > UMAX and e > 0.0) or (u_raw_cand < UMIN and e < 0.0):
            I_new = I_old
            u_raw = ff + P + Ki * I_old
    u_sat = u_raw
    if u_sat > UMAX:
        u_sat = UMAX
    elif u_sat < UMIN:
        u_sat = UMIN
    if not math.isfinite(u_sat):
        u_sat = ff
    if first:
        u = u_sat
    else:
        max_du = RLIM * dt
        du = u_sat - u_prev
        if du > max_du:
            du = max_du
        elif du < -max_du:
            du = -max_du
        u = u_prev + du
    if not math.isfinite(u):
        u = ff
    if u > 1.0:
        u = 1.0
    if u < 0.0:
        u = 0.0
    new_state = {"yf": float(yf), "I": float(I_new), "u": float(u)}
    return float(u), new_state
