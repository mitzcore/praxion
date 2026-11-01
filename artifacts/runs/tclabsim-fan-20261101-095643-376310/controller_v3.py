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
    try:
        y_raw = obs.get("y", 0.5)
    except Exception:
        y_raw = 0.5
    try:
        tgt_raw = obs.get("target", 0.5)
    except Exception:
        tgt_raw = 0.5
    try:
        dt_raw = obs.get("dt", 1.0)
    except Exception:
        dt_raw = 1.0
    try:
        y_m = float(y_raw)
    except Exception:
        y_m = float('nan')
    try:
        tgt = float(tgt_raw)
    except Exception:
        tgt = 0.5
    try:
        dt = float(dt_raw)
    except Exception:
        dt = 1.0
    if not math.isfinite(tgt):
        tgt = 0.5
    tgt = _clamp(tgt, 0.0, 1.0)
    if not math.isfinite(dt) or dt <= 0.0:
        dt = 1.0
    if dt < 0.05:
        dt = 0.05
    if dt > 10.0:
        dt = 10.0
    KP = 0.50
    KI = 0.010
    KD = 3.0
    D_LIM = 0.06
    TAU_F = 4.0
    TAU_S = 20.0
    U_MAX = 0.70
    U_MIN = 0.0
    I_LIM = 0.12
    FF_MIN = 0.25
    FF_MAX = 0.60
    TAU_ADAPT = 250.0
    yf_prev = None
    ys_prev = None
    i_prev = 0.0
    ff_prev = None
    try:
        if isinstance(state, dict):
            v = state.get("yf", None)
            if v is not None:
                vf = float(v)
                if math.isfinite(vf):
                    yf_prev = _clamp(vf, 0.0, 1.0)
            vs = state.get("ys", None)
            if vs is not None:
                vsf = float(vs)
                if math.isfinite(vsf):
                    ys_prev = _clamp(vsf, 0.0, 1.0)
            w = state.get("i", 0.0)
            wf = float(w)
            if math.isfinite(wf):
                i_prev = _clamp(wf, -I_LIM, I_LIM)
            f = state.get("ff", None)
            if f is not None:
                ff0 = float(f)
                if math.isfinite(ff0):
                    ff_prev = _clamp(ff0, FF_MIN, FF_MAX)
    except Exception:
        yf_prev = None
        ys_prev = None
        i_prev = 0.0
        ff_prev = None
    if ff_prev is None:
        ff = _clamp(tgt - 0.05, FF_MIN, FF_MAX)
    else:
        ff = ff_prev
    if not math.isfinite(y_m):
        if yf_prev is None:
            y_m2 = tgt
        else:
            y_m2 = yf_prev
    else:
        y_m2 = _clamp(y_m, 0.0, 1.0)
    if yf_prev is None:
        yf = y_m2
        ys = y_m2
        dy_slow = 0.0
    else:
        af = dt / (TAU_F + dt)
        if af < 0.0:
            af = 0.0
        if af > 1.0:
            af = 1.0
        yf = (1.0 - af) * yf_prev + af * y_m2
        if not math.isfinite(yf):
            yf = y_m2
        yf = _clamp(yf, 0.0, 1.0)
        if ys_prev is None:
            ys = yf
            dy_slow = 0.0
        else:
            a_s = dt / (TAU_S + dt)
            if a_s < 0.0:
                a_s = 0.0
            if a_s > 1.0:
                a_s = 1.0
            ys = (1.0 - a_s) * ys_prev + a_s * y_m2
            if not math.isfinite(ys):
                ys = yf
            ys = _clamp(ys, 0.0, 1.0)
            dy_slow = (ys - ys_prev) / dt
            if not math.isfinite(dy_slow):
                dy_slow = 0.0
            if dy_slow > 0.02:
                dy_slow = 0.02
            if dy_slow < -0.02:
                dy_slow = -0.02
    err = tgt - yf
    if not math.isfinite(err):
        err = 0.0
    p = KP * err
    d = KD * dy_slow
    if d > D_LIM:
        d = D_LIM
    if d < -D_LIM:
        d = -D_LIM
    i_prop = i_prev + KI * err * dt
    i_prop = _clamp(i_prop, -I_LIM, I_LIM)
    u_unsat_prop = ff + p - d + i_prop
    if not math.isfinite(u_unsat_prop):
        u_unsat_prop = ff
    u_sat_prop = _clamp(u_unsat_prop, U_MIN, U_MAX)
    if (u_unsat_prop > U_MAX and err > 0.0) or (u_unsat_prop < U_MIN and err < 0.0):
        i_new = i_prev
    else:
        i_new = i_prop
    u_unsat = ff + p - d + i_new
    if not math.isfinite(u_unsat):
        u_unsat = ff
        i_new = i_prev
    u = _clamp(u_unsat, U_MIN, U_MAX)
    if yf > 0.80:
        u = 0.0
        if i_new > 0.0:
            i_new = 0.0
    elif yf > 0.68:
        if u > 0.25:
            u = 0.25
        if i_new > 0.05:
            i_new = 0.05
    if not math.isfinite(u):
        u = ff
    u = _clamp(u, 0.0, 1.0)
    try:
        if abs(err) < 0.025 and abs(dy_slow) < 0.0007 and yf < 0.68:
            beta = dt / (TAU_ADAPT + dt)
            if beta < 0.0:
                beta = 0.0
            if beta > 1.0:
                beta = 1.0
            ff_new = ff + (u - ff) * beta
            ff_new = _clamp(ff_new, FF_MIN, FF_MAX)
        else:
            ff_new = ff
    except Exception:
        ff_new = ff
    new_state = {"yf": float(yf), "ys": float(ys), "i": float(i_new), "ff": float(ff_new)}
    return (float(u), new_state)
