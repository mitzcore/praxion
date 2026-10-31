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
        if not math.isfinite(y_in):
            y_tmp = state.get("yf", 0.6)
            if not math.isfinite(y_tmp):
                y_tmp = 0.6
            y_in = y_tmp
        if not math.isfinite(t_in):
            t_in = 0.6
        if not math.isfinite(dt_in) or dt_in <= 0:
            dt_in = 0.2
        y = _clamp(y_in, 0.0, 1.0)
        target = _clamp(t_in, 0.0, 1.0)
        dt = y_in * 0.0 + dt_in
        if dt < 0.02:
            dt = 0.02
        if dt > 1.0:
            dt = 1.0
        yf_prev = state.get("yf", None)
        rf_prev = state.get("rf", 0.0)
        integ_prev = state.get("integ", 0.0)
        if not math.isfinite(rf_prev):
            rf_prev = 0.0
        if not math.isfinite(integ_prev):
            integ_prev = 0.0
        rf_prev = _clamp(rf_prev, -0.15, 0.15)
        integ_prev = _clamp(integ_prev, -0.35, 0.35)
        first = True
        if isinstance(yf_prev, float) or isinstance(yf_prev, int):
            if math.isfinite(yf_prev):
                first = False
        if first:
            yf = y
            rf = 0.0
        else:
            yf_prev = _clamp(float(yf_prev), 0.0, 1.0)
            Tf = 1.2
            a = dt / (Tf + dt)
            yf = (1.0 - a) * yf_prev + a * y
            yf = _clamp(yf, 0.0, 1.0)
            raw_rate = (yf - yf_prev) / dt
            raw_rate = _clamp(raw_rate, -0.15, 0.15)
            Tr = 0.8
            b = dt / (Tr + dt)
            rf = (1.0 - b) * rf_prev + b * raw_rate
            rf = _clamp(rf, -0.15, 0.15)
        ff = 1.15 * target
        ff = _clamp(ff, 0.0, 0.80)
        err = target - yf
        err = _clamp(err, -1.0, 1.0)
        if err > 0:
            Kp = 1.1
        else:
            Kp = 2.5
        P = Kp * err
        P = _clamp(P, -0.5, 0.5)
        Kd = 1.0
        D = -Kd * rf
        D = _clamp(D, -0.25, 0.25)
        if yf > 0.80:
            s_max = 0.20
        elif yf > 0.78:
            s_max = 0.40
        elif yf > 0.75:
            s_max = 0.55
        elif yf > 0.72:
            s_max = 0.75
        else:
            s_max = 0.92
        if y > 0.85:
            if s_max > 0.20:
                s_max = 0.20
        Ki = 0.35
        integ = integ_prev
        if abs(err) < 0.25:
            u_test = ff + P + integ + D
            blocked_high = (u_test > s_max) and (err > 0)
            blocked_low = (u_test < 0.0) and (err < 0)
            if not blocked_high and not blocked_low:
                integ = integ + Ki * err * dt
                integ = _clamp(integ, -0.35, 0.35)
        u = ff + P + integ + D
        if u > s_max:
            u = s_max
        if u < 0.0:
            u = 0.0
        if u > 1.0:
            u = 1.0
        if not math.isfinite(u):
            u = 0.0
        ns = {"yf": float(_clamp(yf, 0.0, 1.0)), "rf": float(_clamp(rf, -0.15, 0.15)), "integ": float(_clamp(integ, -0.35, 0.35))}
        return (float(u), ns)
    except Exception:
        try:
            return (0.0, {"yf": 0.6, "rf": 0.0, "integ": 0.0})
        except Exception:
            return (0.0, {})
