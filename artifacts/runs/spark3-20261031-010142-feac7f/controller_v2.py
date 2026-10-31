import math
def _clamp(v, lo, hi):
    if not math.isfinite(v):
        return lo
    if v < lo:
        return lo
    if v > hi:
        return hi
    return v
def control(obs, state):
    try:
        y_raw_in = float(obs.get("y", 0.6))
    except Exception:
        y_raw_in = 0.6
    try:
        target = float(obs.get("target", 0.6))
    except Exception:
        target = 0.6
    try:
        dt_in = float(obs.get("dt", 0.1))
    except Exception:
        dt_in = 0.1
    if not math.isfinite(target):
        target = 0.6
    target = _clamp(target, 0.0, 1.0)
    if not math.isfinite(dt_in) or dt_in <= 0.0:
        dt_in = 0.1
    dt = dt_in
    if dt < 0.02:
        dt = 0.02
    if dt > 0.5:
        dt = 0.5
    try:
        yf_prev = float(state.get("yf", float('nan')))
    except Exception:
        yf_prev = float('nan')
    try:
        d_prev = float(state.get("df", 0.0))
    except Exception:
        d_prev = 0.0
    try:
        integ_prev = float(state.get("integ", 0.0))
    except Exception:
        integ_prev = 0.0
    try:
        u_prev = float(state.get("u_prev", float('nan')))
    except Exception:
        u_prev = float('nan')
    try:
        bias_prev = float(state.get("bias", 0.0))
    except Exception:
        bias_prev = 0.0
    if not math.isfinite(d_prev):
        d_prev = 0.0
    if not math.isfinite(integ_prev):
        integ_prev = 0.0
    if not math.isfinite(bias_prev):
        bias_prev = 0.0
    d_prev = _clamp(d_prev, -0.2, 0.2)
    integ_prev = _clamp(integ_prev, -0.20, 0.20)
    bias_prev = _clamp(bias_prev, -0.10, 0.10)
    y_bad = (not math.isfinite(y_raw_in))
    if y_bad:
        if math.isfinite(yf_prev):
            y_raw = _clamp(yf_prev, 0.0, 1.0)
        else:
            y_raw = target
    else:
        y_raw = _clamp(y_raw_in, 0.0, 1.0)
    if not math.isfinite(yf_prev):
        yf_prev = y_raw
    else:
        yf_prev = _clamp(yf_prev, 0.0, 1.0)
    if not math.isfinite(u_prev):
        ff_init = _clamp(0.883 * target, 0.0, 0.8)
        u_prev = _clamp(ff_init + bias_prev, 0.0, 1.0)
    else:
        u_prev = _clamp(u_prev, 0.0, 1.0)
    tau_f = 1.5
    alpha = dt / (tau_f + dt)
    yf = yf_prev + alpha * (y_raw - yf_prev)
    yf = _clamp(yf, 0.0, 1.0)
    d_raw = (yf - yf_prev) / dt
    if not math.isfinite(d_raw):
        d_raw = 0.0
    d_raw = _clamp(d_raw, -0.2, 0.2)
    tau_d = 2.5
    alpha_d = dt / (tau_d + dt)
    df = d_prev + alpha_d * (d_raw - d_prev)
    if not math.isfinite(df):
        df = d_prev
    df = _clamp(df, -0.2, 0.2)
    e = target - yf
    ff0 = _clamp(0.883 * target, 0.0, 0.8)
    bias = bias_prev
    if abs(e) < 0.08 and abs(df) < 0.015 and not y_bad:
        bias = bias_prev + 0.02 * e * dt
        bias = _clamp(bias, -0.10, 0.10)
    ff = _clamp(ff0 + bias, 0.0, 0.85)
    Kp = 0.38
    Ki = 0.03
    Kd = 1.8
    P = Kp * e
    integ_new = integ_prev + Ki * e * dt
    integ_new = _clamp(integ_new, -0.20, 0.20)
    u_unsat = ff + P + integ_new - Kd * df
    if (u_unsat > 1.0 and e > 0.0) or (u_unsat < 0.0 and e < 0.0):
        integ_new = integ_prev
        u_unsat = ff + P + integ_new - Kd * df
    u = _clamp(u_unsat, 0.0, 1.0)
    T_pred = 7.0
    y_pred = yf + T_pred * df
    y_pred = _clamp(y_pred, 0.0, 1.0)
    capped = False
    if (yf > 0.84) or (not y_bad and y_raw_in > 0.86 and math.isfinite(y_raw_in)):
        if u != 0.0:
            capped = True
        u = 0.0
    elif yf > 0.65 and y_pred > 0.82:
        if u > 0.0:
            capped = True
        u = 0.0
    elif (yf > 0.75) or (yf > 0.65 and y_pred > 0.75):
        if u > 0.25:
            capped = True
            u = 0.25
    elif yf > 0.70 and df > 0.01 and y_pred > 0.70:
        if u > 0.45:
            capped = True
            u = 0.45
    if capped:
        integ_new = integ_prev
    max_du = 0.20 * dt
    du = u - u_prev
    if du > max_du:
        u = u_prev + max_du
    elif du < -max_du:
        u = u_prev - max_du
    u = _clamp(u, 0.0, 1.0)
    if not math.isfinite(u):
        u = ff
        u = _clamp(u, 0.0, 1.0)
    state["yf"] = float(yf)
    state["df"] = float(df)
    state["integ"] = float(integ_new)
    state["u_prev"] = float(u)
    state["bias"] = float(bias)
    return (float(u), state)
