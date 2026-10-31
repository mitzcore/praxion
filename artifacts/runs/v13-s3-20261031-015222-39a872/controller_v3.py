import math
def _clamp(x, lo, hi):
    if x < lo:
        return lo
    if x > hi:
        return hi
    return x
def control(obs, state):
    KP0 = 0.35
    KI0 = 0.030
    KD0 = 0.80
    TAU_F = 2.5
    TAU_R = 4.0
    I_LIM = 4.0
    FF0 = 0.60
    INV_GAIN = 0.5
    T0 = 0.6
    KPEND = 0.045
    try:
        y_raw = float(obs.get("y", 0.6))
    except Exception:
        y_raw = 0.6
    try:
        target = float(obs.get("target", 0.6))
    except Exception:
        target = 0.6
    try:
        dt = float(obs.get("dt", 0.2))
    except Exception:
        dt = 0.2
    try:
        el = float(obs.get("elapsed_s", float("nan")))
    except Exception:
        el = float("nan")
    bad_y = False
    if not math.isfinite(y_raw):
        bad_y = True
        y_raw = None
    if not math.isfinite(target):
        target = 0.6
    if not math.isfinite(dt) or dt <= 0.0:
        dt = 0.2
    if dt < 0.02:
        dt = 0.02
    if dt > 1.0:
        dt = 1.0
    target = _clamp(target, 0.0, 1.0)
    try:
        yf_prev = float(state.get("yf", target if y_raw is None else _clamp(y_raw, 0.0, 1.0)))
    except Exception:
        yf_prev = target
    try:
        I_prev = float(state.get("I", 0.0))
    except Exception:
        I_prev = 0.0
    try:
        rate_prev = float(state.get("rate", 0.0))
    except Exception:
        rate_prev = 0.0
    try:
        u_prev = float(state.get("u_prev", FF0))
    except Exception:
        u_prev = FF0
    try:
        Td = float(state.get("Td", 4.0))
    except Exception:
        Td = 4.0
    try:
        t_prev = float(state.get("t", 0.0))
    except Exception:
        t_prev = 0.0
    try:
        ht = list(state.get("ht", []))
    except Exception:
        ht = []
    try:
        hy = list(state.get("hy", []))
    except Exception:
        hy = []
    try:
        hu = list(state.get("hu", []))
    except Exception:
        hu = []
    if not math.isfinite(yf_prev):
        yf_prev = target
    if not math.isfinite(I_prev):
        I_prev = 0.0
    if not math.isfinite(rate_prev):
        rate_prev = 0.0
    if not math.isfinite(u_prev):
        u_prev = FF0
    if not math.isfinite(Td):
        Td = 4.0
    if not math.isfinite(t_prev):
        t_prev = 0.0
    yf_prev = _clamp(yf_prev, 0.0, 1.0)
    I_prev = _clamp(I_prev, -I_LIM, I_LIM)
    rate_prev = _clamp(rate_prev, -0.2, 0.2)
    u_prev = _clamp(u_prev, 0.0, 1.0)
    Td = _clamp(Td, 3.5, 16.0)
    if math.isfinite(el):
        if el < t_prev - 1.0:
            t_now = t_prev + dt
        else:
            if el < t_prev:
                t_now = t_prev + dt
            else:
                diff = el - t_prev
                if diff > 2.0:
                    t_now = t_prev + dt
                else:
                    t_now = el
                    if t_now <= t_prev:
                        t_now = t_prev + dt
    else:
        t_now = t_prev + dt
    if not math.isfinite(t_now):
        t_now = t_prev + dt
    if y_raw is None:
        y_meas = yf_prev
    else:
        y_meas = _clamp(y_raw, 0.0, 1.0)
    alpha = dt / (TAU_F + dt)
    yf = yf_prev + alpha * (y_meas - yf_prev)
    if not math.isfinite(yf):
        yf = yf_prev
    yf = _clamp(yf, 0.0, 1.0)
    if bad_y:
        yf = yf_prev
    rate_raw = (yf - yf_prev) / dt
    if not math.isfinite(rate_raw):
        rate_raw = 0.0
    rate_raw = _clamp(rate_raw, -0.2, 0.2)
    beta = dt / (TAU_R + dt)
    rate = rate_prev + beta * (rate_raw - rate_prev)
    if not math.isfinite(rate):
        rate = rate_prev
    rate = _clamp(rate, -0.2, 0.2)
    ht.append(float(t_now))
    hy.append(float(yf))
    hu.append(float(u_prev))
    while len(ht) > 0 and ht[0] < t_now - 26.0:
        ht.pop(0)
        hy.pop(0)
        hu.pop(0)
    while len(ht) > 140:
        ht.pop(0)
        hy.pop(0)
        hu.pop(0)
    if len(ht) >= 2 and (t_now - ht[0] >= 6.0):
        W = 7.0
        idx = 0
        for i, tt in enumerate(ht):
            if tt >= t_now - W:
                idx = i
                break
        y_old = hy[idx]
        dy = yf - y_old
        s = 0.0
        c = 0
        for k in range(idx, len(hu)):
            try:
                s += float(hu[k])
            except Exception:
                pass
            c += 1
        umean = s / c if c > 0 else u_prev
        e_obs = target - yf
        if e_obs > 0.12 and umean > 0.70:
            if dy < 0.03:
                Td += dt * 1.2
            elif dy < 0.06:
                Td += dt * 0.4
        if umean < 0.40 and dy > 0.05 and yf > 0.35:
            Td += dt * 1.0
        if e_obs > 0.05 and umean > 0.60 and dy > 0.10:
            Td -= dt * 0.15
        Td = _clamp(Td, 3.5, 16.0)
    ff = FF0 + INV_GAIN * (target - T0)
    ff = _clamp(ff, 0.0, 0.85)
    u_eq = ff
    S = 0.0
    if len(ht) >= 2:
        idxT = 0
        for i, tt in enumerate(ht):
            if tt >= t_now - Td:
                idxT = i
                break
        for k in range(idxT + 1, len(ht)):
            try:
                delta = float(ht[k]) - float(ht[k-1])
            except Exception:
                delta = dt
            if not math.isfinite(delta) or delta < 0.0:
                delta = 0.0
            if delta > 2.0:
                delta = 2.0
            try:
                uk = float(hu[k])
            except Exception:
                uk = u_eq
            S += (uk - u_eq) * delta
        try:
            tail = t_now - float(ht[-1])
        except Exception:
            tail = 0.0
        if not math.isfinite(tail) or tail < 0.0:
            tail = 0.0
        if tail > 2.0:
            tail = 2.0
        S += (u_prev - u_eq) * tail
    if not math.isfinite(S):
        S = 0.0
    S = _clamp(S, -8.0, 12.0)
    y_virt = yf + KPEND * S
    if not math.isfinite(y_virt):
        y_virt = yf
    y_virt = _clamp(y_virt, 0.0, 1.0)
    scale = 4.0 / Td
    scale = _clamp(scale, 0.25, 1.15)
    Kp = KP0 * (scale ** 0.7)
    Ki = KI0 * (scale ** 1.4)
    if Td < 9.0:
        Kd = KD0 * scale
    else:
        Kd = 0.0
    e_virt = target - y_virt
    if not math.isfinite(e_virt):
        e_virt = 0.0
    e_p = _clamp(e_virt, -0.4, 0.4)
    p = Kp * e_p
    I_try = I_prev + e_virt * dt
    I_try = _clamp(I_try, -I_LIM, I_LIM)
    u_try = ff + p + Ki * I_try - Kd * rate
    sat_hi = u_try > 1.0 and e_virt > 0.0
    sat_lo = u_try < 0.0 and e_virt < 0.0
    if sat_hi or sat_lo:
        I_new = I_prev
        u_raw = ff + p + Ki * I_new - Kd * rate
    else:
        I_new = I_try
        u_raw = u_try
    if not math.isfinite(u_raw):
        u_raw = ff
        I_new = I_prev
    if not math.isfinite(I_new):
        I_new = I_prev
    I_new = _clamp(I_new, -I_LIM, I_LIM)
    u_raw = _clamp(u_raw, 0.0, 1.0)
    max_up = 0.25 * scale * dt
    max_down = 0.60 * dt
    if max_up < 0.01 * dt:
        max_up = 0.01 * dt
    du = u_raw - u_prev
    if du > 0.0:
        if du > max_up:
            du = max_up
    else:
        if du < -max_down:
            du = -max_down
    u = u_prev + du
    u = _clamp(u, 0.0, 1.0)
    h = min(Td, 8.0)
    y_ahead = y_virt + (rate if rate > 0.0 else 0.0) * h * 0.7
    if not math.isfinite(y_ahead):
        y_ahead = y_virt
    y_ahead = _clamp(y_ahead, 0.0, 1.2)
    if yf > 0.84 or y_ahead > 0.88:
        u = 0.0
    elif yf > 0.78 or y_ahead > 0.80:
        if u > 0.12:
            u = 0.12
    elif (yf > 0.72 and rate > 0.015) or (y_ahead > 0.73 and rate > 0.01):
        if u > 0.35:
            u = 0.35
    if not math.isfinite(u):
        u = _clamp(ff, 0.0, 1.0)
    u = _clamp(float(u), 0.0, 1.0)
    new_state = {"yf": float(yf), "I": float(I_new), "rate": float(rate), "u_prev": float(u), "Td": float(Td), "t": float(t_now), "ht": [float(x) for x in ht], "hy": [float(x) for x in hy], "hu": [float(x) for x in hu]}
    return (u, new_state)
