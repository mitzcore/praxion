import math
def _ff_for_target(t):
    try:
        tt = float(t)
    except Exception:
        tt = 0.5
    if not math.isfinite(tt):
        tt = 0.5
    if tt < 0.0:
        tt = 0.0
    if tt > 1.0:
        tt = 1.0
    if tt <= 0.07:
        ff = 0.0
    elif tt <= 0.438:
        ff = 0.3 * (tt - 0.07) / 0.368
    elif tt <= 0.515:
        ff = 0.3 + (tt - 0.438) / 0.77
    elif tt <= 0.54:
        ff = 0.4 + (tt - 0.515) / 0.25
    else:
        ff = 0.5 + (tt - 0.54) / 0.25
    if not math.isfinite(ff):
        ff = 0.38
    if ff < 0.0:
        ff = 0.0
    if ff > 1.0:
        ff = 1.0
    return ff
def control(obs, state):
    try:
        y_raw = float(obs.get("y", 0.5))
    except Exception:
        y_raw = 0.5
    try:
        tgt_raw = float(obs.get("target", 0.5))
    except Exception:
        tgt_raw = 0.5
    try:
        dt_raw = float(obs.get("dt", 1.0))
    except Exception:
        dt_raw = 1.0
    if not math.isfinite(dt_raw) or dt_raw <= 0.0:
        dt = 1.0
    else:
        dt = dt_raw
        if dt < 0.2:
            dt = 0.2
        if dt > 5.0:
            dt = 5.0
    if not math.isfinite(tgt_raw):
        tgt = 0.5
    else:
        tgt = tgt_raw
        if tgt < 0.0:
            tgt = 0.0
        if tgt > 1.0:
            tgt = 1.0
    if not isinstance(state, dict):
        state = {}
    try:
        yf_prev = float(state.get("yf", y_raw))
    except Exception:
        yf_prev = 0.5
    try:
        i_prev = float(state.get("i", 0.0))
    except Exception:
        i_prev = 0.0
    if not math.isfinite(yf_prev):
        yf_prev = 0.5
    if not math.isfinite(i_prev):
        i_prev = 0.0
    if yf_prev < 0.0:
        yf_prev = 0.0
    if yf_prev > 1.0:
        yf_prev = 1.0
    if i_prev > 0.65:
        i_prev = 0.65
    if i_prev < -0.30:
        i_prev = -0.30
    if not math.isfinite(y_raw):
        y_meas = yf_prev
    else:
        y_meas = y_raw
        if y_meas < 0.0:
            y_meas = 0.0
        if y_meas > 1.0:
            y_meas = 1.0
    kp = 1.2
    ki = 0.022
    tf = 10.0
    i_max = 0.65
    i_min = -0.30
    u_max = 1.0
    u_min = 0.0
    e_en = 0.20
    alpha = dt / (tf + dt)
    yf = (1.0 - alpha) * yf_prev + alpha * y_meas
    if not math.isfinite(yf):
        yf = yf_prev
    if yf < 0.0:
        yf = 0.0
    if yf > 1.0:
        yf = 1.0
    ff = _ff_for_target(tgt)
    e = tgt - yf
    if not math.isfinite(e):
        e = 0.0
    u_before = ff + kp * e + i_prev
    can = True
    ae = e if e >= 0.0 else -e
    if ae > e_en:
        can = False
    elif u_before > u_max and e > 0.0:
        can = False
    elif u_before < u_min and e < 0.0:
        can = False
    i_new = i_prev
    if can:
        i_new = i_prev + ki * e * dt
        if i_new > i_max:
            i_new = i_max
        if i_new < i_min:
            i_new = i_min
    if not math.isfinite(i_new):
        i_new = i_prev
    u = ff + kp * e + i_new
    if not math.isfinite(u):
        u = ff
    if u > u_max:
        u = u_max
    if u < u_min:
        u = u_min
    if y_meas >= 0.84 or yf >= 0.84:
        u = 0.0
        if i_new > 0.0:
            i_new = 0.0
    if u < 0.0:
        u = 0.0
    if u > 1.0:
        u = 1.0
    if not math.isfinite(u):
        u = 0.0
    nxt = {"yf": float(yf), "i": float(i_new)}
    return (float(u), nxt)
