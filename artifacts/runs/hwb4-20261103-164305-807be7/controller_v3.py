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

def control(obs: dict, state: dict) -> tuple[float, dict]:
    Kp = 0.75
    Ki = 0.014
    Tf = 12.0
    UMAX = 0.95
    UMIN = 0.0
    RLIM = 0.06
    I_AUTH = 0.35
    Kb = 0.008
    TSLOW = 50.0
    SET_THR = 0.05
    SET_HOLD = 15.0
    B_MIN = -0.10
    B_MAX = 0.25
    K_NOM = 1.352
    AMB = 0.17
    K_MIN = 0.35
    K_MAX = 1.80
    K_TAU = 80.0
    try:
        y_raw = obs.get("y", 0.5)
        tgt = obs.get("target", 0.5)
        dt_in = obs.get("dt", 1.0)
    except Exception:
        return 0.24, {"yf": 0.5, "ys": 0.5, "us": 0.24, "I": 0.0, "bias": 0.0, "st": 0.0, "u": 0.24, "Kest": 1.352}
    if not isinstance(state, dict):
        state = {}
    try:
        y_in = float(y_raw)
    except Exception:
        y_in = float(state.get("yf", 0.5))
    try:
        target = float(tgt)
    except Exception:
        target = 0.5
    try:
        dt = float(dt_in)
    except Exception:
        dt = 1.0
    if not math.isfinite(y_in):
        y_in = float(state.get("yf", 0.5))
        if not math.isfinite(y_in):
            y_in = 0.5
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
    y = y_in
    if y < -0.2:
        y = -0.2
    if y > 1.2:
        y = 1.2
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
        ys_prev = float(state.get("ys", yf_prev))
    except Exception:
        ys_prev = yf_prev
    if not math.isfinite(ys_prev):
        ys_prev = yf_prev
    if ys_prev < 0.0:
        ys_prev = 0.0
    if ys_prev > 1.0:
        ys_prev = 1.0
    try:
        us_prev = float(state.get("us", 0.24))
    except Exception:
        us_prev = 0.24
    if not math.isfinite(us_prev):
        us_prev = 0.24
    if us_prev < UMIN:
        us_prev = UMIN
    if us_prev > UMAX:
        us_prev = UMAX
    try:
        I_old = float(state.get("I", 0.0))
    except Exception:
        I_old = 0.0
    if not math.isfinite(I_old):
        I_old = 0.0
    try:
        bias_old = float(state.get("bias", 0.0))
    except Exception:
        bias_old = 0.0
    if not math.isfinite(bias_old):
        bias_old = 0.0
    if bias_old < B_MIN:
        bias_old = B_MIN
    if bias_old > B_MAX:
        bias_old = B_MAX
    try:
        st_old = float(state.get("st", 0.0))
    except Exception:
        st_old = 0.0
    if not math.isfinite(st_old) or st_old < 0.0:
        st_old = 0.0
    if st_old > 500.0:
        st_old = 500.0
    try:
        u_prev = float(state.get("u", 0.24))
    except Exception:
        u_prev = 0.24
    if not math.isfinite(u_prev):
        u_prev = 0.24
    if u_prev < UMIN:
        u_prev = UMIN
    if u_prev > UMAX:
        u_prev = UMAX
    try:
        Kest = float(state.get("Kest", K_NOM))
    except Exception:
        Kest = K_NOM
    if not math.isfinite(Kest):
        Kest = K_NOM
    if Kest < K_MIN:
        Kest = K_MIN
    if Kest > K_MAX:
        Kest = K_MAX
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
    a_s = dt / (TSLOW + dt)
    ys = ys_prev + a_s * (yf - ys_prev)
    if not math.isfinite(ys):
        ys = ys_prev
    us = us_prev + a_s * (u_prev - us_prev)
    if not math.isfinite(us):
        us = us_prev
    if ys < 0.0:
        ys = 0.0
    if ys > 1.0:
        ys = 1.0
    if us < UMIN:
        us = UMIN
    if us > UMAX:
        us = UMAX
    if abs(yf - ys) < SET_THR:
        st_new = st_old + dt
    else:
        st_new = 0.0
    if st_new > 500.0:
        st_new = 500.0
    Kest_new = Kest
    if (not first) and st_new > SET_HOLD and us > 0.12 and ys > 0.25 and ys < 0.85 and us < 0.9:
        denom = us if us > 0.08 else 0.08
        Kraw = (ys - AMB) / denom
        if Kraw < K_MIN:
            Kraw = K_MIN
        if Kraw > K_MAX:
            Kraw = K_MAX
        ak = dt / (K_TAU + dt)
        Kest_new = Kest + ak * (Kraw - Kest)
        if not math.isfinite(Kest_new):
            Kest_new = Kest
        if Kest_new < K_MIN:
            Kest_new = K_MIN
        if Kest_new > K_MAX:
            Kest_new = K_MAX
    ff_nom = _ff_for_target(target)
    scale = K_NOM / Kest_new if Kest_new > 0.1 else 1.0
    if scale < 0.6:
        scale = 0.6
    if scale > 3.0:
        scale = 3.0
    ff = ff_nom * scale
    if ff < UMIN:
        ff = UMIN
    if ff > UMAX:
        ff = UMAX
    e = target - yf
    I_lim = I_AUTH / Ki if Ki != 0 else 1e6
    I_cand = I_old + e * dt
    if I_cand > I_lim:
        I_cand = I_lim
    elif I_cand < -I_lim:
        I_cand = -I_lim
    P = Kp * e
    I_new = I_cand
    u_test_fast = ff + P + Ki * I_cand + bias_old
    if abs(e) > 0.15:
        I_new = I_old
    else:
        if (u_test_fast > UMAX and e > 0.0) or (u_test_fast < UMIN and e < 0.0):
            I_new = I_old
    bias_new = bias_old
    if (not first) and st_new > SET_HOLD and us > 0.08 and abs(e) < 0.12:
        if abs(e) > 0.008:
            bc = bias_old + Kb * e * dt
            if bc > B_MAX:
                bc = B_MAX
            elif bc < B_MIN:
                bc = B_MIN
            u_test2 = ff + P + Ki * I_new + bc
            if (u_test2 > UMAX and e > 0.0) or (u_test2 < UMIN and e < 0.0):
                bias_new = bias_old
            else:
                bias_new = bc
    elif first:
        bias_new = bias_old
    u_raw = ff + P + Ki * I_new + bias_new
    if not math.isfinite(u_raw):
        u_raw = ff
        I_new = I_old
        bias_new = bias_old
    u_sat = u_raw
    if u_sat > UMAX:
        u_sat = UMAX
    elif u_sat < UMIN:
        u_sat = UMIN
    if yf > 0.82:
        u_sat = UMIN
        I_new = I_old
        bias_new = bias_old
        st_new = 0.0
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
    new_state = {"yf": float(yf), "ys": float(ys), "us": float(us), "I": float(I_new), "bias": float(bias_new), "st": float(st_new), "u": float(u), "Kest": float(Kest_new)}
    return float(u), new_state
