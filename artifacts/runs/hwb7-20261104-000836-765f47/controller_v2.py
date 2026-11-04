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
        y0 = 0.135
        kp = 1.0
        ki = 0.025
        I_LIM = 0.35
        tau_f = 12.0
        tau_s = 35.0
        tau_u = 35.0
        tau_k = 50.0
        first = ("yf" not in state) or ("integ" not in state) or ("Kest" not in state)
        if first:
            if y_meas0 is None:
                y_init = target
            else:
                y_init = _clamp(y_meas0, 0.0, 1.0)
            yf_prev = y_init
            ys_prev = y_init
            Kest_prev = 1.05
            integ_prev = 0.0
            uff_init = (target - y0) / 1.05
            uff_init = _clamp(uff_init, 0.0, 0.85)
            uf_prev = uff_init
            u_prev = None
            t_prev = 0.0
        else:
            try:
                yf_prev = float(state.get("yf", 0.5))
            except Exception:
                yf_prev = 0.5
            if not math.isfinite(yf_prev):
                yf_prev = 0.5
            yf_prev = _clamp(yf_prev, 0.0, 1.0)
            try:
                ys_prev = float(state.get("ys", yf_prev))
            except Exception:
                ys_prev = yf_prev
            if not math.isfinite(ys_prev):
                ys_prev = yf_prev
            ys_prev = _clamp(ys_prev, 0.0, 1.0)
            try:
                uf_prev = float(state.get("uf", 0.34))
            except Exception:
                uf_prev = 0.34
            if not math.isfinite(uf_prev):
                uf_prev = 0.34
            uf_prev = _clamp(uf_prev, 0.0, 1.0)
            try:
                Kest_prev = float(state.get("Kest", 1.05))
            except Exception:
                Kest_prev = 1.05
            if not math.isfinite(Kest_prev):
                Kest_prev = 1.05
            Kest_prev = _clamp(Kest_prev, 0.35, 1.30)
            try:
                integ_prev = float(state.get("integ", 0.0))
            except Exception:
                integ_prev = 0.0
            if not math.isfinite(integ_prev):
                integ_prev = 0.0
            integ_prev = _clamp(integ_prev, -I_LIM, I_LIM)
            try:
                up = state.get("u_prev", None)
                if isinstance(up, (int, float)) and math.isfinite(float(up)):
                    u_prev = _clamp(float(up), 0.0, 1.0)
                else:
                    u_prev = None
            except Exception:
                u_prev = None
            try:
                t_prev = float(state.get("t", 0.0))
            except Exception:
                t_prev = 0.0
            if not math.isfinite(t_prev) or t_prev < 0.0:
                t_prev = 0.0
            if y_meas0 is None:
                y_meas0 = yf_prev
        if y_meas0 is None:
            y_meas = yf_prev if not first else target
        else:
            y_meas = _clamp(float(y_meas0), 0.0, 1.0)
            if first:
                yf_prev = y_meas
                ys_prev = y_meas
        alpha_f = dt / (tau_f + dt)
        max_innov = 0.06 + 0.006 * dt
        innov = y_meas - yf_prev
        if innov > max_innov:
            innov = max_innov
        elif innov < -max_innov:
            innov = -max_innov
        yf = yf_prev + alpha_f * innov
        yf = _clamp(yf, 0.0, 1.0)
        alpha_s = dt / (tau_s + dt)
        ys = ys_prev + alpha_s * (yf - ys_prev)
        ys = _clamp(ys, 0.0, 1.0)
        if u_prev is None:
            uf = uf_prev
        else:
            alpha_u = dt / (tau_u + dt)
            uf = uf_prev + alpha_u * (u_prev - uf_prev)
            uf = _clamp(uf, 0.0, 1.0)
        t = t_prev + dt
        Kest = Kest_prev
        if t > 60.0 and uf > 0.15 and uf < 0.90 and yf > (y0 + 0.03) and yf < 0.80:
            if abs(yf - ys) < 0.020:
                denom = uf
                if denom < 0.15:
                    denom = 0.15
                Kraw = (ys - y0) / denom
                if math.isfinite(Kraw):
                    if Kraw < 0.35:
                        Kraw = 0.35
                    if Kraw > 1.30:
                        Kraw = 1.30
                    alpha_k = dt / (tau_k + dt)
                    Kest = Kest_prev + alpha_k * (Kraw - Kest_prev)
                    Kest = _clamp(Kest, 0.35, 1.30)
        if Kest < 0.35:
            Kest = 0.35
        if Kest > 1.30:
            Kest = 1.30
        uff = (target - y0) / Kest
        uff = _clamp(uff, 0.0, 0.85)
        e = target - yf
        integ_tent = integ_prev + ki * e * dt
        integ_tent = _clamp(integ_tent, -I_LIM, I_LIM)
        u_unsat_tent = uff + kp * e + integ_tent
        if (u_unsat_tent > 1.0 and e > 0.0) or (u_unsat_tent < 0.0 and e < 0.0):
            integ = integ_prev
        else:
            integ = integ_tent
        u_unsat = uff + kp * e + integ
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
            u = uff
        u = _clamp(float(u), 0.0, 1.0)
        new_state = {"yf": float(yf), "ys": float(ys), "uf": float(uf), "Kest": float(Kest), "integ": float(integ), "u_prev": float(u), "t": float(t)}
        return (float(u), new_state)
    except Exception:
        try:
            yf_f = float(state.get("yf", 0.5))
            if not math.isfinite(yf_f):
                yf_f = 0.5
        except Exception:
            yf_f = 0.5
        yf_f = _clamp(yf_f, 0.0, 1.0)
        try:
            Kf = float(state.get("Kest", 1.05))
            if not math.isfinite(Kf):
                Kf = 1.05
        except Exception:
            Kf = 1.05
        Kf = _clamp(Kf, 0.35, 1.30)
        try:
            uf_f = float(state.get("uf", 0.34))
            if not math.isfinite(uf_f):
                uf_f = 0.34
        except Exception:
            uf_f = 0.34
        return (0.34, {"yf": float(yf_f), "ys": float(yf_f), "uf": float(_clamp(uf_f, 0.0, 1.0)), "Kest": float(Kf), "integ": 0.0, "u_prev": 0.34, "t": 0.0})
