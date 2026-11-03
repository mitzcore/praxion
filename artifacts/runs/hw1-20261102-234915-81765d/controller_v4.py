import math
def _num(x, d):
    try:
        f = float(x)
    except Exception:
        return d
    if not math.isfinite(f):
        return d
    return f
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
        y = _num(obs.get("y", 0.5), 0.5)
        target = _num(obs.get("target", 0.5), 0.5)
        dt = _num(obs.get("dt", 1.0), 1.0)
        if not math.isfinite(dt) or dt <= 0.0:
            dt = 1.0
        if dt < 0.2:
            dt = 0.2
        if dt > 5.0:
            dt = 5.0
        y = _clamp(y, 0.0, 1.0)
        target = _clamp(target, 0.0, 1.0)
        yf_prev = _clamp(_num(state.get("yf", y), y), 0.0, 1.0)
        i_prev = _clamp(_num(state.get("i", 0.0), 0.0), -0.3, 0.3)
        df_prev = _clamp(_num(state.get("df", 0.0), 0.0), -0.05, 0.05)
        ff_raw = state.get("ff", None)
        tgt_raw = state.get("tgt", None)
        try:
            ff_f = float(ff_raw) if ff_raw is not None else None
            if ff_f is None or not math.isfinite(ff_f):
                ff_f = None
        except Exception:
            ff_f = None
        try:
            tgt_f = float(tgt_raw) if tgt_raw is not None else None
            if tgt_f is None or not math.isfinite(tgt_f):
                tgt_f = None
        except Exception:
            tgt_f = None
        if ff_f is None or tgt_f is None:
            ff_adapt = 0.322 + 0.90 * (target - 0.5)
        else:
            ff_adapt = ff_f + 0.90 * (target - tgt_f)
        ff_adapt = _clamp(ff_adapt, 0.05, 0.75)
        Kp = 0.45
        Ki_base = 0.010
        Tp = 70.0
        Tf = 10.0
        Td = 18.0
        Imin = -0.12
        Imax = 0.12
        Umax = 0.75
        alpha = dt / (Tf + dt)
        yf = alpha * y + (1.0 - alpha) * yf_prev
        yf = _clamp(yf, 0.0, 1.0)
        e = target - yf
        draw = _clamp((yf - yf_prev) / dt, -0.05, 0.05)
        beta = dt / (Td + dt)
        df_new = _clamp(beta * draw + (1.0 - beta) * df_prev, -0.05, 0.05)
        e_pred = _clamp(e - Tp * df_new, -0.6, 0.6)
        p = _clamp(Kp * e_pred, -0.30, 0.30)
        ae = abs(e)
        if ae > 0.15:
            kieff = 0.0
        elif ae > 0.08:
            kieff = Ki_base * 0.30
        else:
            kieff = Ki_base
        icand = _clamp(i_prev + kieff * e * dt, Imin, Imax)
        u_raw = ff_adapt + p + icand
        if (u_raw > Umax and e > 0.0) or (u_raw < 0.0 and e < 0.0):
            integ_new = i_prev
            u_raw = ff_adapt + p + integ_new
        else:
            integ_new = icand
        u = _clamp(u_raw, 0.0, Umax)
        if yf > 0.80:
            u = 0.0
        elif yf > 0.70:
            if u > 0.20:
                u = 0.20
        ff_new = ff_adapt
        try:
            settled = (abs(e) < 0.035) and (abs(df_new) < 0.0009) and (yf < 0.68) and (u > 0.02) and (u < Umax - 0.02)
            if settled:
                lam = 0.004 * dt
                if lam > 0.05:
                    lam = 0.05
                delta = lam * (u - ff_adapt)
                if delta > 0.003:
                    delta = 0.003
                if delta < -0.003:
                    delta = -0.003
                ff_proposed = _clamp(ff_adapt + delta, 0.05, 0.75)
                actual = ff_proposed - ff_adapt
                ff_new = ff_proposed
                integ_new = _clamp(integ_new - actual, Imin, Imax)
                u = _clamp(ff_new + p + integ_new, 0.0, Umax)
                if yf > 0.80:
                    u = 0.0
                elif yf > 0.70:
                    if u > 0.20:
                        u = 0.20
        except Exception:
            ff_new = ff_adapt
        if not math.isfinite(yf):
            yf = y
        if not math.isfinite(df_new):
            df_new = 0.0
        if not math.isfinite(integ_new):
            integ_new = 0.0
        if not math.isfinite(ff_new):
            ff_new = ff_adapt
        if not math.isfinite(u):
            u = _clamp(ff_new, 0.0, Umax)
        u = _clamp(float(u), 0.0, 1.0)
        nstate = {"yf": float(_clamp(yf, 0.0, 1.0)), "i": float(_clamp(integ_new, -0.3, 0.3)), "df": float(_clamp(df_new, -0.05, 0.05)), "ff": float(_clamp(ff_new, 0.05, 0.75)), "tgt": float(target)}
        return float(u), nstate
    except Exception:
        try:
            return float(0.322), {"yf": 0.5, "i": 0.0, "df": 0.0, "ff": 0.322, "tgt": 0.5}
        except Exception:
            return 0.0, {}
