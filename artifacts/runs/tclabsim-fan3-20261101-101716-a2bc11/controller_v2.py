import math
def _clamp(v, lo, hi):
    if not math.isfinite(v):
        return lo
    if v < lo:
        return lo
    if v > hi:
        return hi
    return v
def _num(x, fb):
    try:
        f = float(x)
    except:
        return fb
    if not math.isfinite(f):
        return fb
    return f
def control(obs, state):
    if not isinstance(state, dict):
        state = {}
    try:
        o_y = float(obs.get("y", 0.5))
    except:
        o_y = 0.5
    try:
        o_t = float(obs.get("target", 0.5))
    except:
        o_t = 0.5
    try:
        o_dt = float(obs.get("dt", 1.0))
    except:
        o_dt = 1.0
    if not math.isfinite(o_y):
        o_y = 0.5
    if not math.isfinite(o_t):
        o_t = 0.5
    if not math.isfinite(o_dt) or o_dt <= 0.0:
        o_dt = 1.0
    dt = o_dt
    if dt < 0.1:
        dt = 0.1
    if dt > 10.0:
        dt = 10.0
    y = _clamp(o_y, 0.0, 1.0)
    tgt = _clamp(o_t, 0.0, 1.0)
    yf_old = _clamp(_num(state.get("yf", y), y), 0.0, 1.0)
    uf_old = _clamp(_num(state.get("uf", 0.0), 0.0), 0.0, 1.0)
    integ_old = _clamp(_num(state.get("integ", 0.0), 0.0), -0.35, 0.35)
    Khat_old = _clamp(_num(state.get("Khat", 0.95), 0.95), 0.45, 1.25)
    stable_old = _clamp(_num(state.get("stable", 0.0), 0.0), 0.0, 80.0)
    u_prev = _clamp(_num(state.get("u_prev", 0.0), 0.0), 0.0, 1.0)
    YA = 0.075
    Tf = 10.0
    Tu = 30.0
    alpha = dt / (Tf + dt)
    alpha_u = dt / (Tu + dt)
    yf = yf_old + alpha * (y - yf_old)
    yf = _clamp(yf, 0.0, 1.0)
    uf = uf_old + alpha_u * (u_prev - uf_old)
    uf = _clamp(uf, 0.0, 1.0)
    slope = (yf - yf_old) / dt
    if not math.isfinite(slope):
        slope = 0.0
    cond = (abs(slope) < 0.0006 and uf > 0.15 and yf > 0.14 and yf < 0.78 and abs(u_prev - uf) < 0.05)
    if cond:
        stable = stable_old + dt
    else:
        stable = 0.0
    if stable > 80.0:
        stable = 80.0
    Khat = Khat_old
    if stable >= 60.0:
        denom = uf
        if denom < 0.15:
            denom = 0.15
        Kobs = (yf - YA) / denom
        Kobs = _clamp(Kobs, 0.45, 1.25)
        Khat = Khat_old + 0.07 * (Kobs - Khat_old)
        Khat = _clamp(Khat, 0.45, 1.25)
    ff = (tgt - YA) / Khat if Khat > 0.2 else 0.4
    ff = _clamp(ff, 0.0, 0.70)
    Kp = 1.3
    Ki = 0.022
    U_MIN = 0.0
    U_MAX = 0.75
    INT_LIM = 0.25
    e = tgt - yf
    if not math.isfinite(e):
        e = 0.0
    integ = integ_old + Ki * e * dt
    integ = _clamp(integ, -INT_LIM, INT_LIM)
    u_raw = ff + Kp * e + integ
    if not math.isfinite(u_raw):
        u_raw = ff
        integ = integ_old
    u = _clamp(u_raw, U_MIN, U_MAX)
    if (u_raw > U_MAX and e > 0.0) or (u_raw < U_MIN and e < 0.0):
        integ = integ_old
        u_raw2 = ff + Kp * e + integ
        u = _clamp(u_raw2, U_MIN, U_MAX)
    if yf > 0.82:
        u = 0.0
        if integ > 0.0:
            integ = 0.0
    if not math.isfinite(u):
        u = ff
    u = _clamp(u, 0.0, 1.0)
    nstate = {"yf": float(yf), "uf": float(uf), "integ": float(integ), "Khat": float(Khat), "stable": float(stable), "u_prev": float(u)}
    return (float(u), nstate)
