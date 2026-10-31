import math
def _clamp(v, lo, hi):
    if v < lo:
        return lo
    if v > hi:
        return hi
    return v
def _sanitize(x, fallback):
    try:
        f = float(x)
    except:
        return fallback
    if not math.isfinite(f):
        return fallback
    return f
def control(obs, state):
    try:
        if not isinstance(state, dict):
            state = {}
    except:
        state = {}
    try:
        y_in = obs.get("y", 0.5)
    except:
        y_in = 0.5
    try:
        t_in = obs.get("target", 0.6)
    except:
        t_in = 0.6
    try:
        dt_in = obs.get("dt", 0.1)
    except:
        dt_in = 0.1
    y_raw = _clamp(_sanitize(y_in, 0.5), 0.0, 1.0)
    target = _clamp(_sanitize(t_in, 0.6), 0.0, 1.0)
    dt = _sanitize(dt_in, 0.1)
    if not math.isfinite(dt):
        dt = 0.1
    if dt < 0.02:
        dt = 0.02
    if dt > 1.0:
        dt = 1.0
    Kest = 0.88
    Kp = 1.8
    Ti = 10.0
    Ki = Kp / Ti
    Tf = 1.0
    Umax = 0.85
    Umin = 0.0
    Imax = 0.35
    Imin = -0.35
    Tref = 4.0
    Rrate = 0.04
    Rup = 0.6
    Rdown = 2.0
    try:
        yf_s = state.get("yf", None)
        yf0 = float(yf_s)
        if not math.isfinite(yf0):
            yf0 = y_raw
        else:
            yf0 = _clamp(yf0, 0.0, 1.0)
    except:
        yf0 = y_raw
    try:
        r_s = state.get("r", None)
        if r_s is None:
            r0 = yf0
        else:
            r0 = float(r_s)
            if not math.isfinite(r0):
                r0 = yf0
            else:
                r0 = _clamp(r0, 0.0, 1.0)
    except:
        r0 = yf0
    try:
        i_s = state.get("integ", 0.0)
        integ = float(i_s)
        if not math.isfinite(integ):
            integ = 0.0
        integ = _clamp(integ, Imin, Imax)
    except:
        integ = 0.0
    try:
        up_s = state.get("u_prev", None)
        if up_s is None:
            u_prev = None
        else:
            u_prev = float(up_s)
            if not math.isfinite(u_prev):
                u_prev = None
            else:
                u_prev = _clamp(u_prev, 0.0, 1.0)
    except:
        u_prev = None
    alpha = dt / (Tf + dt)
    if alpha < 0.0:
        alpha = 0.0
    if alpha > 1.0:
        alpha = 1.0
    yf = yf0 + alpha * (y_raw - yf0)
    yf = _clamp(yf, 0.0, 1.0)
    dr_des = (target - r0) * dt / Tref
    dr_lim = Rrate * dt
    if dr_des > dr_lim:
        dr_des = dr_lim
    if dr_des < -dr_lim:
        dr_des = -dr_lim
    r = _clamp(r0 + dr_des, 0.0, 1.0)
    e = r - yf
    ff = r / Kest
    if ff > Umax:
        ff = Umax
    if ff < Umin:
        ff = Umin
    P = Kp * e
    integ_prop = integ + Ki * e * dt
    integ_prop = _clamp(integ_prop, Imin, Imax)
    u_unsat = ff + P + integ_prop
    if (u_unsat > Umax and e > 0.0) or (u_unsat < Umin and e < 0.0):
        integ_new = integ
    else:
        integ_new = integ_prop
    u = ff + P + integ_new
    if u > Umax:
        u = Umax
    if u < Umin:
        u = Umin
    hard = False
    if yf > 0.83 or y_raw > 0.86:
        hard = True
    if yf > 0.75 and not hard:
        allow = Umax - 4.0 * (yf - 0.75)
        if allow < 0.0:
            allow = 0.0
        if u > allow:
            u = allow
    if hard:
        u = 0.0
        if integ_new > 0.0:
            integ_new = 0.0
    else:
        if u_prev is not None:
            du = u - u_prev
            up_lim = Rup * dt
            down_lim = Rdown * dt
            if du > up_lim:
                u = u_prev + up_lim
            elif du < -down_lim:
                u = u_prev - down_lim
    u = _clamp(u, 0.0, 1.0)
    if not math.isfinite(u):
        u = 0.0
        integ_new = 0.0
    try:
        state["yf"] = float(yf)
        state["r"] = float(r)
        state["integ"] = float(integ_new)
        state["u_prev"] = float(u)
    except:
        try:
            state = {"yf": float(yf), "r": float(r), "integ": float(integ_new), "u_prev": float(u)}
        except:
            state = {}
    return (float(u), state)
