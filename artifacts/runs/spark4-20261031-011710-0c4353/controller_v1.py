import math
def _clamp(v, lo, hi):
    if not math.isfinite(v):
        return (lo + hi) * 0.5
    if v < lo:
        return lo
    if v > hi:
        return hi
    return v
def _alpha(dt, tau):
    if tau <= 0.0:
        return 1.0
    a = dt / (tau + dt)
    if a < 0.0:
        return 0.0
    if a > 1.0:
        return 1.0
    return a
def control(obs, state):
    ff = 0.54
    kp = 0.90
    ki = 0.08
    kd = 0.45
    tau_f = 0.7
    tau_d = 1.2
    ramp = 0.03
    i_lo = -0.22
    i_hi = 0.22
    try:
        y_raw = float(obs.get("y", 0.6))
    except Exception:
        y_raw = 0.6
    try:
        target = float(obs.get("target", 0.6))
    except Exception:
        target = 0.6
    try:
        dt_in = float(obs.get("dt", 0.1))
    except Exception:
        dt_in = 0.1
    if not math.isfinite(y_raw):
        y_raw = 0.6
    if not math.isfinite(target):
        target = 0.6
    if not math.isfinite(dt_in) or dt_in <= 0.0:
        dt_in = 0.1
    dt = dt_in
    if dt < 0.02:
        dt = 0.02
    if dt > 1.0:
        dt = 1.0
    y_c = _clamp(y_raw, 0.0, 1.0)
    target_c = _clamp(target, 0.0, 1.0)
    first = (not isinstance(state, dict)) or (len(state) == 0)
    if first:
        yf_prev = y_c
        dfilt_prev = 0.0
        integ_prev = 0.0
        rsp_prev = y_c
        prev_u = ff
    else:
        try:
            yf_prev = float(state.get("yf", y_c))
        except Exception:
            yf_prev = y_c
        try:
            dfilt_prev = float(state.get("dfilt", 0.0))
        except Exception:
            dfilt_prev = 0.0
        try:
            integ_prev = float(state.get("integ", 0.0))
        except Exception:
            integ_prev = 0.0
        try:
            rsp_prev = float(state.get("rsp", yf_prev))
        except Exception:
            rsp_prev = yf_prev
        try:
            prev_u = float(state.get("prev_u", ff))
        except Exception:
            prev_u = ff
        if not math.isfinite(yf_prev):
            yf_prev = y_c
        if not math.isfinite(dfilt_prev):
            dfilt_prev = 0.0
        if not math.isfinite(integ_prev):
            integ_prev = 0.0
        if not math.isfinite(rsp_prev):
            rsp_prev = yf_prev
        if not math.isfinite(prev_u):
            prev_u = ff
        yf_prev = _clamp(yf_prev, 0.0, 1.0)
        rsp_prev = _clamp(rsp_prev, 0.0, 1.0)
        integ_prev = _clamp(integ_prev, i_lo, i_hi)
        prev_u = _clamp(prev_u, 0.0, 1.0)
    a = _alpha(dt, tau_f)
    if first:
        yf = y_c
    else:
        yf = yf_prev + a * (y_c - yf_prev)
    yf = _clamp(yf, 0.0, 1.0)
    if first:
        rsp = yf
    else:
        diff = target_c - rsp_prev
        step = ramp * dt
        if diff > step:
            rsp = rsp_prev + step
        elif diff < -step:
            rsp = rsp_prev - step
        else:
            rsp = target_c
    rsp = _clamp(rsp, 0.0, 1.0)
    if first or dt <= 0.0:
        rate_raw = 0.0
    else:
        rate_raw = (yf - yf_prev) / dt
    if not math.isfinite(rate_raw):
        rate_raw = 0.0
    if rate_raw > 0.5:
        rate_raw = 0.5
    if rate_raw < -0.5:
        rate_raw = -0.5
    b = _alpha(dt, tau_d)
    if first:
        dfilt = 0.0
    else:
        dfilt = dfilt_prev + b * (rate_raw - dfilt_prev)
    if not math.isfinite(dfilt):
        dfilt = 0.0
    if dfilt > 0.2:
        dfilt = 0.2
    if dfilt < -0.2:
        dfilt = -0.2
    e = rsp - yf
    if not math.isfinite(e):
        e = 0.0
    if e > 1.0:
        e = 1.0
    if e < -1.0:
        e = -1.0
    p_term = kp * e
    integ_prop = integ_prev + ki * e * dt
    integ_prop = _clamp(integ_prop, i_lo, i_hi)
    u_test = ff + p_term + integ_prop - kd * dfilt
    if (u_test > 1.0 and e > 0.0) or (u_test < 0.0 and e < 0.0):
        integ = integ_prev
    else:
        integ = integ_prop
    u = ff + p_term + integ - kd * dfilt
    if not math.isfinite(u):
        u = ff
        integ = integ_prev
    if yf > 0.80:
        if u > 0.25:
            u = 0.25
    elif yf > 0.75:
        if u > 0.40:
            u = 0.40
    if y_raw > 0.83 or yf > 0.84:
        u = 0.0
    u = _clamp(u, 0.0, 1.0)
    if not first:
        max_du = 3.0 * dt + 0.02
        du = u - prev_u
        if du > max_du:
            u = prev_u + max_du
        elif du < -max_du:
            u = prev_u - max_du
        u = _clamp(u, 0.0, 1.0)
        if y_raw > 0.83 or yf > 0.84:
            u = 0.0
    new_state = {"yf": float(yf), "integ": float(integ), "dfilt": float(dfilt), "rsp": float(rsp), "prev_u": float(u)}
    return (float(u), new_state)
