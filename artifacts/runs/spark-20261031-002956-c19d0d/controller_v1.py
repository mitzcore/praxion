import math

def _ff_for_target(t):
    if not math.isfinite(t):
        return 0.58
    if t <= 0.0:
        return 0.0
    if t > 1.0:
        t = 1.0
    if t <= 0.32:
        return 0.5 * t / 0.32
    if t <= 0.40:
        return 0.50 + (t - 0.32) * 0.625
    if t <= 0.70:
        return 0.55 + (t - 0.40) * 0.15
    v = 0.595 + (t - 0.70) * 1.0
    if v > 0.85:
        v = 0.85
    if v < 0.0:
        v = 0.0
    return v

def control(obs, state):
    y_raw = obs.get("y", 0.6)
    tgt_raw = obs.get("target", 0.6)
    dt_raw = obs.get("dt", 0.1)
    try:
        y = float(y_raw)
    except Exception:
        y = 0.6
    try:
        target = float(tgt_raw)
    except Exception:
        target = 0.6
    try:
        dt = float(dt_raw)
    except Exception:
        dt = 0.1
    if not math.isfinite(y):
        y = 0.6
    if not math.isfinite(target):
        target = 0.6
    if not math.isfinite(dt) or dt <= 0.0:
        dt = 0.1
    if y < 0.0:
        y = 0.0
    if y > 1.0:
        y = 1.0
    if target < 0.0:
        target = 0.0
    if target > 1.0:
        target = 1.0
    if dt < 0.02:
        dt = 0.02
    if dt > 0.5:
        dt = 0.5
    Kp = 0.55
    Ki = 0.045
    beta = 0.9
    Tf = 0.9
    ff = _ff_for_target(target)
    first = False
    try:
        _ = state.get("yf")
        if _ is None:
            first = True
    except Exception:
        first = True
    if first:
        yf = y
        integ = 0.0
        prev_u = ff
        if prev_u < 0.0:
            prev_u = 0.0
        if prev_u > 1.0:
            prev_u = 1.0
    else:
        try:
            prev_yf = float(state.get("yf", y))
        except Exception:
            prev_yf = y
        try:
            integ_old_tmp = float(state.get("integ", 0.0))
        except Exception:
            integ_old_tmp = 0.0
        try:
            prev_u_tmp = float(state.get("prev_u", ff))
        except Exception:
            prev_u_tmp = ff
        if not math.isfinite(prev_yf):
            prev_yf = y
        if not math.isfinite(integ_old_tmp):
            integ_old_tmp = 0.0
        if not math.isfinite(prev_u_tmp):
            prev_u_tmp = ff
        if prev_yf < 0.0:
            prev_yf = 0.0
        if prev_yf > 1.0:
            prev_yf = 1.0
        if integ_old_tmp < -0.6:
            integ_old_tmp = -0.6
        if integ_old_tmp > 0.4:
            integ_old_tmp = 0.4
        if prev_u_tmp < 0.0:
            prev_u_tmp = 0.0
        if prev_u_tmp > 1.0:
            prev_u_tmp = 1.0
        alpha = dt / (Tf + dt)
        yf = prev_yf + alpha * (y - prev_yf)
        if not math.isfinite(yf):
            yf = prev_yf
        if yf < 0.0:
            yf = 0.0
        if yf > 1.0:
            yf = 1.0
        integ = integ_old_tmp
        prev_u = prev_u_tmp
    e = target - yf
    e_prop = beta * target - yf
    p_term = Kp * e_prop
    far_low = yf < (target - 0.12)
    far_high = yf > (target + 0.10)
    absolute_high = yf > 0.82
    if absolute_high or far_low or far_high:
        pass
    else:
        if e > 0.35:
            e_for_i = 0.35
        elif e < -0.35:
            e_for_i = -0.35
        else:
            e_for_i = e
        integ = integ + Ki * e_for_i * dt
        if integ < -0.6:
            integ = -0.6
        if integ > 0.4:
            integ = 0.4
    old_integ = integ
    pi_u = ff + p_term + integ
    if not math.isfinite(pi_u):
        pi_u = ff
    if pi_u < -1.0:
        pi_u = -1.0
    if pi_u > 2.0:
        pi_u = 2.0
    if yf > 0.82:
        u_target = 0.0
    elif far_high:
        u_target = 0.0
    elif yf > (target + 0.04):
        m = pi_u
        if m > 0.30:
            m = 0.30
        u_target = m
    elif far_low:
        u_target = 0.82
    elif yf < (target - 0.06):
        m2 = pi_u
        if m2 < 0.68:
            m2 = 0.68
        u_target = m2
    else:
        u_target = pi_u
    if y > 0.86:
        u_target = 0.0
    elif y > 0.84:
        if u_target > 0.10:
            u_target = 0.10
    if not math.isfinite(u_target):
        u_target = ff
    if u_target < 0.0:
        u_target = 0.0
    if u_target > 1.0:
        u_target = 1.0
    if first:
        u = u_target
    else:
        max_up = 0.7 * dt
        max_down = 2.0 * dt
        du = u_target - prev_u
        if du > max_up:
            du = max_up
        if du < -max_down:
            du = -max_down
        u = prev_u + du
        if u < 0.0:
            u = 0.0
        if u > 1.0:
            u = 1.0
        if (u >= 0.99 and e > 0.0) or (u <= 0.01 and e < 0.0):
            integ = old_integ
            if (u >= 0.99 and e > 0.0) and integ > 0.2:
                integ = 0.2
    if not math.isfinite(u):
        u = ff
        integ = old_integ
    if u < 0.0:
        u = 0.0
    if u > 1.0:
        u = 1.0
    new_state = {"yf": float(yf), "integ": float(integ), "prev_u": float(u)}
    return (float(u), new_state)
