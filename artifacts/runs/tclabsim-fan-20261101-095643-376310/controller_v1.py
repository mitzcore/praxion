import math

def _clamp(x, lo, hi):
    if not math.isfinite(x):
        return lo
    if x < lo:
        return lo
    if x > hi:
        return hi
    return float(x)

def control(obs, state):
    y_raw = obs.get("y", 0.5)
    tgt_raw = obs.get("target", 0.5)
    dt_raw = obs.get("dt", 1.0)
    try:
        y_m = float(y_raw)
    except Exception:
        y_m = 0.5
    try:
        tgt = float(tgt_raw)
    except Exception:
        tgt = 0.5
    try:
        dt = float(dt_raw)
    except Exception:
        dt = 1.0
    if not math.isfinite(y_m):
        y_m = 0.5
    if not math.isfinite(tgt):
        tgt = 0.5
    if not math.isfinite(dt) or dt <= 0.0:
        dt = 1.0
    if dt > 5.0:
        dt = 5.0
    if dt < 0.05:
        dt = 0.05
    y_m = _clamp(y_m, 0.0, 1.0)
    tgt = _clamp(tgt, 0.0, 1.0)
    U_FF = 0.45
    KP = 0.8
    KI = 0.005
    U_MAX = 0.70
    U_MIN = 0.0
    I_LIM = 0.20
    TAU_F = 12.0
    yf_prev = None
    i_prev = 0.0
    try:
        if isinstance(state, dict):
            v = state.get("yf", None)
            if v is not None:
                vf = float(v)
                if math.isfinite(vf):
                    yf_prev = _clamp(vf, 0.0, 1.0)
            w = state.get("i", 0.0)
            wf = float(w)
            if math.isfinite(wf):
                i_prev = _clamp(wf, -I_LIM, I_LIM)
    except Exception:
        yf_prev = None
        i_prev = 0.0
    if yf_prev is None:
        yf = y_m
    else:
        alpha = dt / (TAU_F + dt)
        if alpha < 0.0:
            alpha = 0.0
        if alpha > 1.0:
            alpha = 1.0
        yf = (1.0 - alpha) * yf_prev + alpha * y_m
        if not math.isfinite(yf):
            yf = y_m
        yf = _clamp(yf, 0.0, 1.0)
    err = tgt - yf
    if not math.isfinite(err):
        err = 0.0
    p = KP * err
    i_prop = i_prev + KI * err * dt
    i_prop = _clamp(i_prop, -I_LIM, I_LIM)
    u_unsat_prop = U_FF + p + i_prop
    u_sat_prop = _clamp(u_unsat_prop, U_MIN, U_MAX)
    if (u_unsat_prop > U_MAX and err > 0.0) or (u_unsat_prop < U_MIN and err < 0.0):
        i_new = i_prev
    else:
        i_new = i_prop
    u_unsat = U_FF + p + i_new
    u = _clamp(u_unsat, U_MIN, U_MAX)
    if yf > 0.80:
        u = 0.0
        if i_new > 0.0:
            i_new = 0.0
    elif yf > 0.70:
        if u > 0.20:
            u = 0.20
        if i_new > 0.05:
            i_new = 0.05
    if not math.isfinite(u):
        u = U_FF
        i_new = i_prev
    u = _clamp(u, 0.0, 1.0)
    new_state = {"yf": float(yf), "i": float(i_new)}
    return (float(u), new_state)
