import math
def _clamp(v, lo, hi):
    if not math.isfinite(v):
        return (lo + hi) * 0.5
    if v < lo:
        return lo
    if v > hi:
        return hi
    return v
def control(obs, state):
    try:
        if not isinstance(state, dict):
            state = {}
        try:
            y_in = obs.get("y", 0.6)
            t_in = obs.get("target", 0.6)
            dt_in = obs.get("dt", 0.2)
        except Exception:
            y_in = 0.6
            t_in = 0.6
            dt_in = 0.2
        yf_s = state.get("yf", None)
        y_use_for_nan = None
        if isinstance(yf_s, (float, int)) and math.isfinite(float(yf_s)):
            y_use_for_nan = float(yf_s)
        else:
            y_use_for_nan = 0.6
        if not math.isfinite(y_in):
            y_in = y_use_for_nan
        if not math.isfinite(t_in):
            t_in = 0.6
        if not math.isfinite(dt_in) or dt_in <= 0:
            dt_in = 0.2
        y = _clamp(float(y_in), 0.0, 1.0)
        target = _clamp(float(t_in), 0.0, 1.0)
        dt = float(dt_in)
        if dt < 0.02:
            dt = 0.02
        if dt > 1.0:
            dt = 1.0
        yf_prev = state.get("yf", None)
        rf_prev = state.get("rf", 0.0)
        integ_prev = state.get("integ", 0.0)
        uprev = state.get("uprev", None)
        uff_prev = state.get("uff", 0.62)
        if not math.isfinite(rf_prev):
            rf_prev = 0.0
        if not math.isfinite(integ_prev):
            integ_prev = 0.0
        if not math.isfinite(uff_prev):
            uff_prev = 0.62
        rf_prev = _clamp(float(rf_prev), -0.15, 0.15)
        integ_prev = _clamp(float(integ_prev), -0.30, 0.30)
        uff = _clamp(float(uff_prev), 0.35, 0.85)
        if isinstance(uprev, (float, int)) and math.isfinite(float(uprev)):
            uprev = _clamp(float(uprev), 0.0, 1.0)
        else:
            uprev = None
        first = True
        if isinstance(yf_prev, (float, int)) and math.isfinite(float(yf_prev)):
            first = False
        if first:
            yf = y
            rf = 0.0
        else:
            yfp = _clamp(float(yf_prev), 0.0, 1.0)
            Tf = 2.0
            a = dt / (Tf + dt)
            yf = (1.0 - a) * yfp + a * y
            yf = _clamp(yf, 0.0, 1.0)
            raw = (yf - yfp) / dt
            raw = _clamp(raw, -0.15, 0.15)
            Tr = 2.5
            b = dt / (Tr + dt)
            rf = (1.0 - b) * rf_prev + b * raw
            rf = _clamp(rf, -0.15, 0.15)
        Tp = 6.0
        y_pred = yf + Tp * rf
        y_pred = _clamp(y_pred, 0.0, 1.0)
        err = target - yf
        err_pred = target - y_pred
        err = _clamp(err, -1.0, 1.0)
        err_pred = _clamp(err_pred, -1.0, 1.0)
        Kp = 0.75
        Kd = 1.0
        Ki = 0.07
        P = Kp * err_pred
        P = _clamp(P, -0.30, 0.30)
        D = -Kd * rf
        D = _clamp(D, -0.15, 0.15)
        if yf > 0.78:
            s_max = 0.30
        elif yf > 0.73:
            s_max = 0.45
        elif yf > 0.68:
            s_max = 0.60
        elif yf > 0.64:
            s_max = 0.75
        else:
            s_max = 0.90
        if y > 0.83:
            s_max = 0.20
        elif y > 0.80:
            if s_max > 0.30:
                s_max = 0.30
        integ = integ_prev
        if abs(err) < 0.22 and abs(err) > 0.015:
            u_test = uff + P + integ + D
            blocked_high = (u_test > s_max) and (err > 0)
            blocked_low = (u_test < 0.0) and (err < 0)
            pred_block = (y_pred > target + 0.04) and (err > 0)
            if (not blocked_high) and (not blocked_low) and (not pred_block):
                integ = integ + Ki * err * dt
                integ = _clamp(integ, -0.30, 0.30)
        u = uff + P + integ + D
        if y_pred > target:
            over = y_pred - target
            cap_pred = uff - 0.9 * over
            if u > cap_pred:
                u = cap_pred
        if u > s_max:
            u = s_max
        if u < 0.0:
            u = 0.0
        if u > 1.0:
            u = 1.0
        if uprev is not None:
            up_lim = uprev + 0.25 * dt
            dn_lim = uprev - 0.40 * dt
            if u > up_lim:
                u = up_lim
            elif u < dn_lim:
                u = dn_lim
        if not math.isfinite(u):
            u = uff
        u = _clamp(u, 0.0, 1.0)
        if abs(err) < 0.09 and abs(rf) < 0.007:
            if yf > 0.30 and yf < 0.80:
                uff = uff + 0.05 * err * dt
                uff = _clamp(uff, 0.35, 0.85)
        ns = {"yf": float(_clamp(yf, 0.0, 1.0)), "rf": float(_clamp(rf, -0.15, 0.15)), "integ": float(_clamp(integ, -0.30, 0.30)), "uprev": float(u), "uff": float(uff)}
        return (float(u), ns)
    except Exception:
        try:
            return (0.0, {"yf": 0.6, "rf": 0.0, "integ": 0.0, "uprev": 0.0, "uff": 0.62})
        except Exception:
            return (0.0, {})
