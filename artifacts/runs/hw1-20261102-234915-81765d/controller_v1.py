import math

def _num(x, d):
    try:
        f = float(x)
    except Exception:
        return d
    if not math.isfinite(f):
        return d
    return f

def control(obs, state):
    try:
        if not isinstance(state, dict):
            state = {}
        y = _num(obs.get("y", 0.5), 0.5)
        target = _num(obs.get("target", 0.5), 0.5)
        dt = _num(obs.get("dt", 1.0), 1.0)
        if dt <= 0.0 or not math.isfinite(dt):
            dt = 1.0
        if dt < 0.2:
            dt = 0.2
        if dt > 5.0:
            dt = 5.0
        if y < 0.0:
            y = 0.0
        if y > 1.0:
            y = 1.0
        if target < 0.0:
            target = 0.0
        if target > 1.0:
            target = 1.0
        yf_prev = _num(state.get("yf", y), y)
        integ_prev = _num(state.get("i", 0.0), 0.0)
        df_prev = _num(state.get("df", 0.0), 0.0)
        if yf_prev < 0.0:
            yf_prev = 0.0
        if yf_prev > 1.0:
            yf_prev = 1.0
        if integ_prev < -0.3:
            integ_prev = -0.3
        if integ_prev > 0.3:
            integ_prev = 0.3
        if df_prev < -0.05:
            df_prev = -0.05
        if df_prev > 0.05:
            df_prev = 0.05
        Kp = 0.7
        Ki = 0.01
        Kd = 8.0
        Tf = 12.0
        Td = 20.0
        Imin = -0.25
        Imax = 0.25
        Umax = 0.75
        ff = 0.322 + 0.7018 * (target - 0.5)
        if ff < 0.0:
            ff = 0.0
        if ff > 0.65:
            ff = 0.65
        alpha = dt / (Tf + dt)
        yf = alpha * y + (1.0 - alpha) * yf_prev
        e = target - yf
        p = Kp * e
        draw = (yf - yf_prev) / dt
        if draw < -0.05:
            draw = -0.05
        if draw > 0.05:
            draw = 0.05
        beta = dt / (Td + dt)
        df_new = beta * draw + (1.0 - beta) * df_prev
        dterm = -Kd * df_new
        if dterm < -0.12:
            dterm = -0.12
        if dterm > 0.12:
            dterm = 0.12
        if abs(e) < 0.15:
            kieff = Ki
        else:
            kieff = Ki * 0.2
        icand = integ_prev + kieff * e * dt
        if icand < Imin:
            icand = Imin
        if icand > Imax:
            icand = Imax
        u_raw = ff + p + icand + dterm
        integ_new = icand
        if (u_raw > Umax and e > 0.0) or (u_raw < 0.0 and e < 0.0):
            integ_new = integ_prev
            u_raw = ff + p + integ_new + dterm
        u = u_raw
        if u < 0.0:
            u = 0.0
        if u > Umax:
            u = Umax
        if yf > 0.80:
            u = 0.0
        elif yf > 0.70:
            if u > 0.15:
                u = 0.15
        if not math.isfinite(u):
            u = ff
            if u < 0.0:
                u = 0.0
            if u > Umax:
                u = Umax
        if not math.isfinite(yf):
            yf = y
        if not math.isfinite(df_new):
            df_new = 0.0
        nstate = {"yf": float(yf), "i": float(integ_new), "df": float(df_new)}
        if u < 0.0:
            u = 0.0
        if u > 1.0:
            u = 1.0
        if not math.isfinite(u):
            u = 0.0
        return float(u), nstate
    except Exception:
        try:
            return float(0.322), {"yf": 0.5, "i": 0.0, "df": 0.0}
        except Exception:
            return 0.0, {}
