import math
def _clamp(v, lo, hi):
    if v < lo:
        return lo
    if v > hi:
        return hi
    return v
def control(obs, state):
    y_m = 0.5
    tgt = 0.5
    dt = 1.0
    try:
        y_m = float(obs["y"])
    except Exception:
        y_m = 0.5
    try:
        tgt = float(obs["target"])
    except Exception:
        tgt = 0.5
    try:
        dt = float(obs["dt"])
    except Exception:
        dt = 1.0
    if not math.isfinite(y_m):
        y_m = 0.5
    if not math.isfinite(tgt):
        tgt = 0.5
    if not math.isfinite(dt) or dt <= 0.0:
        dt = 1.0
    if dt < 0.05:
        dt = 0.05
    if dt > 5.0:
        dt = 5.0
    if y_m < 0.0:
        y_m = 0.0
    if y_m > 1.0:
        y_m = 1.0
    if tgt < 0.0:
        tgt = 0.0
    if tgt > 1.0:
        tgt = 1.0
    if state is None:
        state = {}
    yf = state.get("yf", None)
    integ = state.get("integ", 0.0)
    Kest = state.get("Kest", 0.885)
    u_avg = state.get("u_avg", None)
    y_avg = state.get("y_avg", None)
    dy = state.get("dy", 0.0)
    prev_yf = state.get("prev_yf", None)
    prev_u = state.get("prev_u", None)
    elapsed = state.get("elapsed", 0.0)
    prev_tgt = state.get("prev_tgt", None)
    try:
        yf = float(yf)
    except Exception:
        yf = y_m
    try:
        integ = float(integ)
    except Exception:
        integ = 0.0
    try:
        Kest = float(Kest)
    except Exception:
        Kest = 0.885
    try:
        dy = float(dy)
    except Exception:
        dy = 0.0
    try:
        elapsed = float(elapsed)
    except Exception:
        elapsed = 0.0
    try:
        u_avg = float(u_avg) if u_avg is not None else None
    except Exception:
        u_avg = None
    try:
        y_avg = float(y_avg) if y_avg is not None else None
    except Exception:
        y_avg = None
    try:
        prev_yf = float(prev_yf) if prev_yf is not None else None
    except Exception:
        prev_yf = None
    try:
        prev_u = float(prev_u) if prev_u is not None else None
    except Exception:
        prev_u = None
    try:
        prev_tgt = float(prev_tgt) if prev_tgt is not None else None
    except Exception:
        prev_tgt = None
    if not math.isfinite(yf):
        yf = y_m
    if not math.isfinite(integ):
        integ = 0.0
    if not math.isfinite(Kest):
        Kest = 0.885
    if not math.isfinite(dy):
        dy = 0.0
    if not math.isfinite(elapsed):
        elapsed = 0.0
    yf = _clamp(yf, 0.0, 1.0)
    integ = _clamp(integ, -0.40, 0.55)
    Kest = _clamp(Kest, 0.42, 1.15)
    # target jump: reset slow memories to avoid stale average
    tgt_changed = False
    if prev_tgt is not None and math.isfinite(prev_tgt):
        if abs(tgt - prev_tgt) > 0.02:
            tgt_changed = True
    # filter y
    Tf = 8.0
    Kp = 2.2
    Ki = 0.032
    yamb = 0.05
    alpha = dt / (Tf + dt)
    yf = yf + alpha * (y_m - yf)
    yf = _clamp(yf, 0.0, 1.0)
    elapsed = elapsed + dt
    # slow averages for gain estimation
    Ts = 70.0
    alps = dt / (Ts + dt)
    if u_avg is None or not math.isfinite(u_avg):
        u_avg = prev_u if (prev_u is not None and math.isfinite(prev_u)) else 0.508
    if y_avg is None or not math.isfinite(y_avg):
        y_avg = yf
    if tgt_changed:
        y_avg = yf
        dy = 0.0
        if prev_u is not None and math.isfinite(prev_u):
            u_avg = prev_u
    else:
        if prev_u is not None and math.isfinite(prev_u):
            u_avg = u_avg + alps * (prev_u - u_avg)
        y_avg = y_avg + alps * (yf - y_avg)
    u_avg = _clamp(u_avg, 0.0, 1.0)
    y_avg = _clamp(y_avg, 0.0, 1.0)
    # derivative of filtered y
    if prev_yf is None or not math.isfinite(prev_yf):
        prev_yf = yf
        dy = 0.0
    else:
        raw = (yf - prev_yf) / dt
        if raw > 0.02:
            raw = 0.02
        if raw < -0.02:
            raw = -0.02
        if not math.isfinite(raw):
            raw = 0.0
        alpd = dt / (12.0 + dt)
        dy = dy + alpd * (raw - dy)
        if not math.isfinite(dy):
            dy = 0.0
        if dy > 0.02:
            dy = 0.02
        if dy < -0.02:
            dy = -0.02
    e = tgt - yf
    # adapt Kest near steady state only
    if (not tgt_changed) and (prev_u is not None) and math.isfinite(prev_u):
        if elapsed > 90.0 and u_avg > 0.22 and y_avg > 0.12 and yf < 0.80:
            if abs(e) < 0.22 and abs(dy) < 0.0012:
                if abs(prev_u - u_avg) < 0.07 and abs(yf - y_avg) < 0.03:
                    if prev_u > 0.02 and prev_u < 0.98:
                        denom = u_avg
                        if denom < 0.15:
                            denom = 0.15
                        Kraw = (y_avg - yamb) / denom
                        Kraw = _clamp(Kraw, 0.35, 1.20)
                        if math.isfinite(Kraw):
                            old_uff = _clamp((tgt - yamb) / Kest, 0.0, 1.0)
                            newK = Kest + (dt / 90.0) * (Kraw - Kest)
                            newK = _clamp(newK, 0.42, 1.15)
                            new_uff = _clamp((tgt - yamb) / newK, 0.0, 1.0)
                            delta = new_uff - old_uff
                            Kest = newK
                            integ = integ - delta
                            integ = _clamp(integ, -0.40, 0.55)
    uff = (tgt - yamb) / Kest
    uff = _clamp(uff, 0.0, 1.0)
    prop = Kp * e
    u_test = uff + prop + integ
    blocked_high = (u_test >= 1.0) and (e > 0.0)
    blocked_low = (u_test <= 0.0) and (e < 0.0)
    if not (blocked_high or blocked_low):
        integ = integ + Ki * e * dt
        integ = _clamp(integ, -0.40, 0.55)
    u = uff + prop + integ
    u = _clamp(u, 0.0, 1.0)
    if yf > 0.85:
        u = 0.0
    elif yf > 0.80:
        if u > 0.20:
            u = 0.20
    if not math.isfinite(u):
        u = _clamp(uff, 0.0, 1.0)
    state["yf"] = float(yf)
    state["integ"] = float(integ)
    state["Kest"] = float(Kest)
    state["u_avg"] = float(u_avg)
    state["y_avg"] = float(y_avg)
    state["dy"] = float(dy)
    state["prev_yf"] = float(yf)
    state["prev_u"] = float(u)
    state["elapsed"] = float(elapsed)
    state["prev_tgt"] = float(tgt)
    return float(u), state
