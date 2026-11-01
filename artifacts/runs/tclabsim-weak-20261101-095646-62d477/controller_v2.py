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
        uff_prev = state.get("uff", None)
        if uff_prev is not None:
            uff_prev = float(uff_prev)
    except Exception:
        uff_prev = None
    amb = 0.05
    ff_nom = target - amb
    if ff_nom < 0.0:
        ff_nom = 0.0
    if ff_nom > 1.0:
        ff_nom = 1.0
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
    if integ_prev < -0.18:
        integ_prev = -0.18
    if integ_prev > 0.18:
        integ_prev = 0.18
    if uff_prev is None or not math.isfinite(uff_prev):
        uff_prev = ff_nom
    if uff_prev < 0.30:
        uff_prev = 0.30
    if uff_prev > 0.80:
        uff_prev = 0.80
    # if target jumped far, pull uff toward new nominal slowly to avoid stale bias
    # small pull only, main adaptation is via error integration
    if y_meas is None:
        y_meas_use = yf_prev
    else:
        y_meas_use = y_meas
    tau_f = 8.0
    alpha = dt / (tau_f + dt)
    if alpha < 0.0:
        alpha = 0.0
    if alpha > 1.0:
        alpha = 1.0
    yf = yf_prev + alpha * (y_meas_use - yf_prev)
    if not math.isfinite(yf):
        yf = yf_prev
    if yf < 0.0:
        yf = 0.0
    if yf > 1.0:
        yf = 1.0
    Kp = 1.4
    Ki_fast = 0.04
    Ki_slow = 0.025
    I_lim = 0.18
    UFF_LO = 0.30
    UFF_HI = 0.80
    u_hi = ff_nom + 0.40
    if u_hi > 0.85:
        u_hi = 0.85
    if u_hi < 0.60:
        u_hi = 0.60
    u_lo = 0.0
    e = target - yf
    u_tmp = uff_prev + Kp * e + integ_prev
    saturated_hi = u_tmp > u_hi and e > 0.0
    saturated_lo = u_tmp < u_lo and e < 0.0
    frozen = saturated_hi or saturated_lo
    # safety freeze
    if yf >= 0.82 or (y_valid and y_in >= 0.86):
        frozen = True
    if frozen:
        integ_new = integ_prev
        uff_new = uff_prev
    else:
        integ_new = integ_prev + Ki_fast * e * dt
        if integ_new < -I_lim:
            integ_new = -I_lim
        if integ_new > I_lim:
            integ_new = I_lim
        # slow adaptive feedforward only near target and away from safety
        if abs(e) < 0.10 and yf < 0.75:
            uff_new = uff_prev + Ki_slow * e * dt
        else:
            uff_new = uff_prev
        if uff_new < UFF_LO:
            uff_new = UFF_LO
        if uff_new > UFF_HI:
            uff_new = UFF_HI
    u = uff_new + Kp * e + integ_new
    if u > u_hi:
        u = u_hi
    if u < u_lo:
        u = u_lo
    if yf >= 0.82:
        u = 0.0
        if integ_new > 0.0:
            integ_new = 0.0
    if y_valid and y_in >= 0.86:
        u = 0.0
        if integ_new > 0.0:
            integ_new = 0.0
    if not math.isfinite(u):
        u = ff_nom
    if u < 0.0:
        u = 0.0
    if u > 1.0:
        u = 1.0
    state["yf"] = float(yf)
    state["integ"] = float(integ_new)
    state["uff"] = float(uff_new)
    state["u_prev"] = float(u)
    return (float(u), state)
