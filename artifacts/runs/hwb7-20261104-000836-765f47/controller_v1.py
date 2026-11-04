import math
def _clamp(v, lo, hi):
    if v < lo:
        return lo
    if v > hi:
        return hi
    return v
def control(obs, state):
    try:
        y_in = obs.get("y", 0.5)
        t_in = obs.get("target", 0.5)
        dt_in = obs.get("dt", 1.0)
        if isinstance(y_in, (int, float)) and math.isfinite(float(y_in)):
            y_meas0 = float(y_in)
        else:
            y_meas0 = None
        if isinstance(t_in, (int, float)) and math.isfinite(float(t_in)):
            target = float(t_in)
        else:
            target = 0.5
        target = _clamp(target, 0.0, 1.0)
        if isinstance(dt_in, (int, float)) and math.isfinite(float(dt_in)) and float(dt_in) > 0.0:
            dt = float(dt_in)
        else:
            dt = 1.0
        if dt < 0.2:
            dt = 0.2
        if dt > 20.0:
            dt = 20.0
        y0 = 0.145
        kest = 1.05
        ff = (target - y0) / kest
        ff = _clamp(ff, 0.0, 1.0)
        kp = 1.1
        ki = 0.006
        tau_f = 15.0
        i_lo = -0.30
        i_hi = 0.30
        has_yf = "yf" in state
        has_ig = "integ" in state
        first = (not has_yf) or (not has_ig)
        if y_meas0 is None or (not math.isfinite(y_meas0)):
            if first:
                y_meas = target
                yf_prev = target
            else:
                try:
                    yf_prev = float(state.get("yf", target))
                except Exception:
                    yf_prev = target
                if not math.isfinite(yf_prev):
                    yf_prev = target
                yf_prev = _clamp(yf_prev, 0.0, 1.0)
                y_meas = yf_prev
        else:
            y_meas = _clamp(y_meas0, 0.0, 1.0)
            if first:
                yf_prev = y_meas
            else:
                try:
                    yf_prev = float(state.get("yf", y_meas))
                except Exception:
                    yf_prev = y_meas
                if not math.isfinite(yf_prev):
                    yf_prev = y_meas
                yf_prev = _clamp(yf_prev, 0.0, 1.0)
        try:
            integ_prev = float(state.get("integ", 0.0))
        except Exception:
            integ_prev = 0.0
        if not math.isfinite(integ_prev):
            integ_prev = 0.0
        integ_prev = _clamp(integ_prev, i_lo, i_hi)
        try:
            u_pr = state.get("u_prev", None)
            if isinstance(u_pr, (int, float)) and math.isfinite(float(u_pr)):
                u_prev = _clamp(float(u_pr), 0.0, 1.0)
            else:
                u_prev = None
        except Exception:
            u_prev = None
        alpha = dt / (tau_f + dt)
        max_innov = 0.06 + 0.006 * dt
        innov = y_meas - yf_prev
        if innov > max_innov:
            innov = max_innov
        elif innov < -max_innov:
            innov = -max_innov
        yf = yf_prev + alpha * innov
        yf = _clamp(yf, 0.0, 1.0)
        e = target - yf
        integ_tent = integ_prev + e * dt
        integ_tent = _clamp(integ_tent, i_lo, i_hi)
        u_unsat_tent = ff + kp * e + ki * integ_tent
        sat_hi = u_unsat_tent > 1.0
        sat_lo = u_unsat_tent < 0.0
        if (sat_hi and e > 0.0) or (sat_lo and e < 0.0):
            integ = integ_prev
        else:
            integ = integ_tent
        u_unsat = ff + kp * e + ki * integ
        u = _clamp(u_unsat, 0.0, 1.0)
        if yf >= 0.80:
            u = 0.0
            if integ > 0.0:
                integ = 0.0
        elif yf >= 0.75:
            cap = (0.85 - yf) * 2.0
            if cap < 0.0:
                cap = 0.0
            if u > cap:
                u = cap
        if (u_prev is not None) and (not first):
            dv_max = 0.10 * dt + 0.02
            dv = u - u_prev
            if dv > dv_max:
                u = u_prev + dv_max
            elif dv < -dv_max:
                u = u_prev - dv_max
            u = _clamp(u, 0.0, 1.0)
        if not math.isfinite(u):
            u = ff
        u = _clamp(float(u), 0.0, 1.0)
        new_state = {"yf": float(yf), "integ": float(integ), "u_prev": float(u)}
        return (float(u), new_state)
    except Exception:
        try:
            yf_f = float(state.get("yf", 0.5))
            if not math.isfinite(yf_f):
                yf_f = 0.5
        except Exception:
            yf_f = 0.5
        if yf_f < 0.0:
            yf_f = 0.0
        if yf_f > 1.0:
            yf_f = 1.0
        return (0.33, {"yf": float(yf_f), "integ": 0.0, "u_prev": 0.33})
