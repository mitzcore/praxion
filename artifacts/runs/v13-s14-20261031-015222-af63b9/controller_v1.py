import math

def _clamp(x, lo, hi):
    if x < lo:
        return lo
    if x > hi:
        return hi
    return x

def _finite_num(x, default):
    try:
        f = float(x)
    except Exception:
        return default
    if not math.isfinite(f):
        return default
    return f

def control(obs, state):
    y_raw = _finite_num(obs.get("y", 0.6), 0.6)
    target = _finite_num(obs.get("target", 0.6), 0.6)
    dt_raw = _finite_num(obs.get("dt", 0.1), 0.1)
    y_raw = _clamp(y_raw, 0.0, 1.0)
    target = _clamp(target, 0.0, 1.0)
    dt = _clamp(dt_raw, 0.02, 1.0)
    FF = 0.55
    KP = 0.8
    KI = 0.045
    KD = 1.8
    TAU_F = 1.2
    TAU_R = 2.0
    I_MAX = 0.32
    try:
        yf_prev = _finite_num(state.get("yf", y_raw), y_raw)
    except Exception:
        yf_prev = y_raw
    try:
        rate_prev = _finite_num(state.get("rate_f", 0.0), 0.0)
    except Exception:
        rate_prev = 0.0
    try:
        I_prev = _finite_num(state.get("I", 0.0), 0.0)
    except Exception:
        I_prev = 0.0
    yf_prev = _clamp(yf_prev, 0.0, 1.0)
    rate_prev = _clamp(rate_prev, -0.15, 0.15)
    I_prev = _clamp(I_prev, -I_MAX, I_MAX)
    is_first = ("yf" not in state)
    if is_first:
        yf = y_raw
        rate_f = 0.0
        I = 0.0
    else:
        alpha = dt / (TAU_F + dt)
        if not math.isfinite(alpha):
            alpha = 0.1
        alpha = _clamp(alpha, 0.0, 1.0)
        yf = (1.0 - alpha) * yf_prev + alpha * y_raw
        yf = _clamp(yf, 0.0, 1.0)
        inst_rate = (yf - yf_prev) / dt
        inst_rate = _clamp(inst_rate, -0.15, 0.15)
        beta = dt / (TAU_R + dt)
        if not math.isfinite(beta):
            beta = 0.05
        beta = _clamp(beta, 0.0, 1.0)
        rate_f = (1.0 - beta) * rate_prev + beta * inst_rate
        rate_f = _clamp(rate_f, -0.15, 0.15)
        e_tmp = target - yf
        if e_tmp > 0.20:
            I = I_prev
        else:
            I_cand = I_prev + KI * e_tmp * dt
            I = _clamp(I_cand, -I_MAX, I_MAX)
    e = target - yf
    e = _clamp(e, -1.0, 1.0)
    P = KP * e
    P = _clamp(P, -0.6, 0.6)
    D = KD * rate_f
    D = _clamp(D, -0.25, 0.25)
    u_raw = FF + P + I - D
    if not math.isfinite(u_raw):
        u_raw = FF
    if yf > 0.80:
        cap = 0.30
    elif yf > 0.75:
        cap = 0.45
    elif yf > 0.70:
        cap = 0.60
    elif yf > 0.68:
        cap = 0.70
    else:
        cap = 1.0
    u_capped = u_raw
    if u_capped > cap:
        u_capped = cap
    u = _clamp(u_capped, 0.0, 1.0)
    if not is_first:
        saturated_high = (u_raw > cap + 1e-9) or (u_raw > 1.0 + 1e-9)
        saturated_low = (u_raw < 0.0 - 1e-9)
        if (saturated_high and e > 0.0) or (saturated_low and e < 0.0):
            I = I_prev
            u_raw2 = FF + P + I - D
            if math.isfinite(u_raw2):
                u_capped2 = u_raw2
                if u_capped2 > cap:
                    u_capped2 = cap
                u = _clamp(u_capped2, 0.0, 1.0)
    if not math.isfinite(u):
        u = FF
        I = I_prev
    u = _clamp(float(u), 0.0, 1.0)
    new_state = {"yf": float(yf), "rate_f": float(rate_f), "I": float(I)}
    return (u, new_state)
