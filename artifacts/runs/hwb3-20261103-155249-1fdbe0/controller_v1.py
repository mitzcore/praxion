import math
def _clamp(v, lo, hi):
    if v < lo:
        return lo
    if v > hi:
        return hi
    return v
def control(obs, state):
    try:
        if not isinstance(state, dict):
            state = {}
        y_raw_in = obs.get("y", 0.5)
        target_in = obs.get("target", 0.5)
        dt_in = obs.get("dt", 1.0)
        try:
            dt = float(dt_in)
        except Exception:
            dt = 1.0
        if not math.isfinite(dt) or dt <= 0.0:
            dt = 1.0
        if dt < 0.05:
            dt = 0.05
        if dt > 20.0:
            dt = 20.0
        try:
            target = float(target_in)
        except Exception:
            target = 0.5
        if not math.isfinite(target):
            target = 0.5
        target = _clamp(target, 0.0, 1.0)
        try:
            y_raw = float(y_raw_in)
        except Exception:
            y_raw = None
        yf_prev = state.get("yf", None)
        ie_prev = state.get("ie", 0.0)
        try:
            ie_prev = float(ie_prev)
        except Exception:
            ie_prev = 0.0
        if not math.isfinite(ie_prev):
            ie_prev = 0.0
        if yf_prev is not None:
            try:
                yf_prev = float(yf_prev)
            except Exception:
                yf_prev = None
            if yf_prev is not None and not math.isfinite(yf_prev):
                yf_prev = None
        if yf_prev is not None:
            yf_prev = _clamp(yf_prev, 0.0, 1.0)
        ie_prev = _clamp(ie_prev, -25.0, 25.0)
        if y_raw is None or not math.isfinite(y_raw):
            if yf_prev is None:
                y_raw = target
            else:
                y_raw = yf_prev
        y_raw = _clamp(y_raw, 0.0, 1.0)
        tau_f = 12.0
        alpha = dt / (tau_f + dt)
        if yf_prev is None:
            yf = y_raw
        else:
            diff = y_raw - yf_prev
            if diff < -0.04 or diff > 0.06:
                yf = yf_prev + alpha * 0.1 * diff
            else:
                yf = yf_prev + alpha * diff
            yf = _clamp(yf, 0.0, 1.0)
        amb = 0.175
        gain = 1.1
        u_ff = (target - amb) / gain
        u_ff = _clamp(u_ff, 0.0, 1.0)
        kp = 0.9
        ki = 0.008
        int_lim = 25.0
        e = target - yf
        if abs(e) < 0.15:
            ie_new = ie_prev + e * dt
            ie_new = _clamp(ie_new, -int_lim, int_lim)
        else:
            ie_new = ie_prev
        p_term = kp * e
        i_term = ki * ie_new
        u_unsat = u_ff + p_term + i_term
        u = _clamp(u_unsat, 0.0, 1.0)
        if (u_unsat > 1.0 and e > 0.0) or (u_unsat < 0.0 and e < 0.0):
            ie_new = ie_prev
            i_term = ki * ie_new
            u_unsat = u_ff + p_term + i_term
            u = _clamp(u_unsat, 0.0, 1.0)
        if yf > 0.84:
            u = 0.0
            if ie_new > 0.0:
                ie_new = 0.0
        if not math.isfinite(u):
            u = _clamp(u_ff, 0.0, 1.0)
        new_state = {"yf": float(yf), "ie": float(ie_new)}
        return (float(u), new_state)
    except Exception:
        return (0.3, {"yf": 0.5, "ie": 0.0})
