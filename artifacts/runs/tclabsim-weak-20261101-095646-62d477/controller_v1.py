import math
def control(obs, state):
    try:
        y_in = float(obs.get("y", 0.5))
    except Exception:
        y_in = 0.5
    try:
        t_in = float(obs.get("target", 0.5))
    except Exception:
        t_in = 0.5
    try:
        d_in = float(obs.get("dt", 1.0))
    except Exception:
        d_in = 1.0
    if not math.isfinite(t_in):
        t_in = 0.5
    if t_in < 0.0:
        t_in = 0.0
    if t_in > 1.0:
        t_in = 1.0
    target = t_in
    if not math.isfinite(d_in) or d_in <= 0.0:
        d_in = 1.0
    dt = d_in
    if dt < 0.05:
        dt = 0.05
    if dt > 5.0:
        dt = 5.0
    y_valid = math.isfinite(y_in)
    if y_valid:
        y_meas = y_in
        if y_meas < -0.1:
            y_meas = -0.1
        if y_meas > 1.1:
            y_meas = 1.1
    else:
        y_meas = None
    try:
        yf_prev = state.get("yf", None)
        if yf_prev is not None:
            yf_prev = float(yf_prev)
    except Exception:
        yf_prev = None
    try:
        integ_prev = float(state.get("integ", 0.0))
    except Exception:
        integ_prev = 0.0
    try:
        u_prev_s = state.get("u_prev", None)
        if u_prev_s is not None:
            u_prev_s = float(u_prev_s)
    except Exception:
        u_prev_s = None
    if yf_prev is None or not math.isfinite(yf_prev):
        if y_meas is not None:
            yy = y_meas
            if yy < 0.0:
                yy = 0.0
            if yy > 1.0:
                yy = 1.0
            yf_prev = yy
        else:
            yf_prev = target
    if not math.isfinite(integ_prev):
        integ_prev = 0.0
    if integ_prev < -0.20:
        integ_prev = -0.20
    if integ_prev > 0.20:
        integ_prev = 0.20
    if y_meas is None:
        y_meas = yf_prev
    tau_f = 10.0
    alpha = dt / (tau_f + dt)
    if alpha < 0.0:
        alpha = 0.0
    if alpha > 1.0:
        alpha = 1.0
    yf = yf_prev + alpha * (y_meas - yf_prev)
    if not math.isfinite(yf):
        yf = yf_prev
    if yf < 0.0:
        yf = 0.0
    if yf > 1.0:
        yf = 1.0
    amb = 0.05
    ff = target - amb
    if ff < 0.0:
        ff = 0.0
    if ff > 1.0:
        ff = 1.0
    Kp = 1.8
    Ki = 0.025
    I_lim = 0.20
    e = target - yf
    u_hi = ff + 0.35
    if u_hi > 1.0:
        u_hi = 1.0
    if u_hi < 0.6:
        u_hi = 0.6
    u_lo = 0.0
    u_tmp = ff + Kp * e + integ_prev
    do_integ = True
    if (u_tmp > u_hi and e > 0.0) or (u_tmp < u_lo and e < 0.0):
        do_integ = False
    if do_integ:
        integ_new = integ_prev + Ki * e * dt
    else:
        integ_new = integ_prev
    if integ_new < -I_lim:
        integ_new = -I_lim
    if integ_new > I_lim:
        integ_new = I_lim
    u = ff + Kp * e + integ_new
    if u > u_hi:
        u = u_hi
    if u < u_lo:
        u = u_lo
    if yf >= 0.82:
        u = 0.0
        if integ_new > 0.0:
            integ_new = 0.0
    if y_meas >= 0.86:
        u = 0.0
        if integ_new > 0.0:
            integ_new = 0.0
    if not math.isfinite(u):
        u = ff
    if u < 0.0:
        u = 0.0
    if u > 1.0:
        u = 1.0
    state["yf"] = float(yf)
    state["integ"] = float(integ_new)
    state["u_prev"] = float(u)
    return (float(u), state)
