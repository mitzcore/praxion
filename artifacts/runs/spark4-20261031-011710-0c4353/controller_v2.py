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
    FF = 0.52
    KP_N = 0.38
    KI_N = 0.016
    RAMP_N = 0.05
    RATE_N = 0.25
    KP_D = 0.16
    KI_D = 0.006
    RAMP_D = 0.012
    RATE_D = 0.04
    TAU_F = 1.2
    I_LIM = 0.20
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
    t_in = None
    try:
        if "elapsed_s" in obs:
            t_in = float(obs.get("elapsed_s"))
        elif "t" in obs:
            t_in = float(obs.get("t"))
        elif "elapsed" in obs:
            t_in = float(obs.get("elapsed"))
    except Exception:
        t_in = None
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
        integ_prev = 0.0
        rsp_prev = y_c
        prev_u = FF
        t_acc = 0.0
        t_entry = 0.0
        y_entry = y_c
        e_sign = 0.0
        in_large = False
        delay = False
        small_t = 0.0
    else:
        try:
            yf_prev = float(state.get("yf", y_c))
        except Exception:
            yf_prev = y_c
        try:
            integ_prev = float(state.get("integ", 0.0))
        except Exception:
            integ_prev = 0.0
        try:
            rsp_prev = float(state.get("rsp", yf_prev))
        except Exception:
            rsp_prev = yf_prev
        try:
            prev_u = float(state.get("prev_u", FF))
        except Exception:
            prev_u = FF
        try:
            t_acc = float(state.get("t_acc", 0.0))
        except Exception:
            t_acc = 0.0
        try:
            t_entry = float(state.get("t_entry", 0.0))
        except Exception:
            t_entry = 0.0
        try:
            y_entry = float(state.get("y_entry", yf_prev))
        except Exception:
            y_entry = yf_prev
        try:
            e_sign = float(state.get("e_sign", 0.0))
        except Exception:
            e_sign = 0.0
        try:
            in_large = bool(state.get("in_large", False))
        except Exception:
            in_large = False
        try:
            delay = bool(state.get("delay", False))
        except Exception:
            delay = False
        try:
            small_t = float(state.get("small_t", 0.0))
        except Exception:
            small_t = 0.0
        if not math.isfinite(yf_prev):
            yf_prev = y_c
        if not math.isfinite(integ_prev):
            integ_prev = 0.0
        if not math.isfinite(rsp_prev):
            rsp_prev = yf_prev
        if not math.isfinite(prev_u):
            prev_u = FF
        if not math.isfinite(t_acc):
            t_acc = 0.0
        if not math.isfinite(t_entry):
            t_entry = t_acc
        if not math.isfinite(y_entry):
            y_entry = yf_prev
        if not math.isfinite(e_sign):
            e_sign = 0.0
        if not math.isfinite(small_t):
            small_t = 0.0
        yf_prev = _clamp(yf_prev, 0.0, 1.0)
        rsp_prev = _clamp(rsp_prev, 0.0, 1.0)
        y_entry = _clamp(y_entry, 0.0, 1.0)
        integ_prev = _clamp(integ_prev, -I_LIM, I_LIM)
        prev_u = _clamp(prev_u, 0.0, 1.0)
    if t_in is not None and math.isfinite(t_in):
        t_now = t_in
        t_acc_new = t_in
    else:
        if first:
            t_acc_new = dt
        else:
            t_acc_new = t_acc + dt
        t_now = t_acc_new
    a = _alpha(dt, TAU_F)
    if first:
        yf = y_c
    else:
        yf = yf_prev + a * (y_c - yf_prev)
    yf = _clamp(yf, 0.0, 1.0)
    e_det = target_c - yf
    if not math.isfinite(e_det):
        e_det = 0.0
    if not delay:
        if abs(e_det) > 0.06:
            if not in_large:
                in_large = True
                t_entry = t_now
                y_entry = yf
                e_sign = 1.0 if e_det > 0.0 else -1.0
                if e_det == 0.0:
                    e_sign = 0.0
            else:
                s = 1.0 if e_det > 0.0 else (-1.0 if e_det < 0.0 else 0.0)
                if s != 0.0 and e_sign != 0.0 and s * e_sign < 0.0:
                    t_entry = t_now
                    y_entry = yf
                    e_sign = s
                else:
                    elapsed = t_now - t_entry
                    if elapsed < 0.0:
                        t_entry = t_now
                        y_entry = yf
                        elapsed = 0.0
                    if elapsed > 12.0:
                        prog = (yf - y_entry) * e_sign
                        if not math.isfinite(prog):
                            prog = 0.0
                        if prog < 0.025:
                            delay = True
                            in_large = False
                            small_t = 0.0
                        else:
                            t_entry = t_now
                            y_entry = yf
        else:
            in_large = False
    else:
        if abs(e_det) < 0.04:
            small_t = small_t + dt
            if small_t > 15.0:
                delay = False
                in_large = False
                small_t = 0.0
        else:
            small_t = 0.0
    if delay:
        kp = KP_D
        ki = KI_D
        ramp = RAMP_D
        max_rate = RATE_D
    else:
        kp = KP_N
        ki = KI_N
        ramp = RAMP_N
        max_rate = RATE_N
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
    e = rsp - yf
    if not math.isfinite(e):
        e = 0.0
    e = _clamp(e, -1.0, 1.0)
    p_term = kp * e
    integ_prop = integ_prev + ki * e * dt
    integ_prop = _clamp(integ_prop, -I_LIM, I_LIM)
    u_test = FF + p_term + integ_prop
    if (u_test > 1.0 and e > 0.0) or (u_test < 0.0 and e < 0.0):
        integ = integ_prev
    else:
        integ = integ_prop
    u = FF + p_term + integ
    if not math.isfinite(u):
        u = FF
        integ = integ_prev
    u = _clamp(u, 0.0, 1.0)
    if not first:
        max_du = max_rate * dt + 0.005
        du = u - prev_u
        if du > max_du:
            u = prev_u + max_du
        elif du < -max_du:
            u = prev_u - max_du
        u = _clamp(u, 0.0, 1.0)
    if yf > 0.80:
        if u > 0.25:
            u = 0.25
    elif yf > 0.75:
        if u > 0.40:
            u = 0.40
    if y_raw > 0.83 or yf > 0.84:
        u = 0.0
    u = _clamp(u, 0.0, 1.0)
    new_state = {"yf": float(yf), "integ": float(integ), "rsp": float(rsp), "prev_u": float(u), "t_acc": float(t_acc_new), "t_entry": float(t_entry), "y_entry": float(y_entry), "e_sign": float(e_sign), "in_large": bool(in_large), "delay": bool(delay), "small_t": float(small_t)}
    return (float(u), new_state)
