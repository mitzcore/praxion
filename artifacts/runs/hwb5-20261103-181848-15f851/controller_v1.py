import math

def _num(x, d):
    try:
        v = float(x)
    except Exception:
        return d
    if not math.isfinite(v):
        return d
    return v

def control(obs, state):
    y_raw = _num(obs.get("y", 0.5), 0.5)
    target = _num(obs.get("target", 0.5), 0.5)
    dt_raw = _num(obs.get("dt", 1.0), 1.0)
    if not math.isfinite(y_raw):
        y_raw = 0.5
    if not math.isfinite(target):
        target = 0.5
    if target < 0.0:
        target = 0.0
    if target > 1.0:
        target = 1.0
    if y_raw < -0.5:
        y_raw = -0.5
    if y_raw > 1.5:
        y_raw = 1.5
    if not math.isfinite(dt_raw):
        dt_raw = 1.0
    dtc = dt_raw
    if dtc < 0.05:
        dtc = 0.05
    if dtc > 20.0:
        dtc = 20.0
    KP = 1.0
    KI = 0.012
    TF = 15.0
    CLIP = 0.045
    I_MIN = -0.15
    I_MAX = 0.20
    U_MIN = 0.0
    U_MAX = 0.75
    E_EN = 0.15
    KFF = 1.0
    FF_BASE = 0.26
    ff = FF_BASE + (target - 0.5) / KFF
    if ff < 0.0:
        ff = 0.0
    if ff > 0.70:
        ff = 0.70
    try:
        old_yf = float(state.get("yf", y_raw))
        if not math.isfinite(old_yf):
            old_yf = y_raw
    except Exception:
        old_yf = y_raw
    try:
        old_i = float(state.get("i", 0.0))
        if not math.isfinite(old_i):
            old_i = 0.0
    except Exception:
        old_i = 0.0
    if old_yf < 0.0:
        old_yf = 0.0
    if old_yf > 1.0:
        old_yf = 1.0
    if old_i < I_MIN:
        old_i = I_MIN
    if old_i > I_MAX:
        old_i = I_MAX
    first = ("yf" not in state)
    if first:
        yf = y_raw
        if yf < 0.0:
            yf = 0.0
        if yf > 1.0:
            yf = 1.0
    else:
        diff = y_raw - old_yf
        if diff > CLIP:
            diff_c = CLIP
        elif diff < -CLIP:
            diff_c = -CLIP
        else:
            diff_c = diff
        yc = old_yf + diff_c
        a = dtc / (TF + dtc)
        yf = old_yf + a * (yc - old_yf)
        if not math.isfinite(yf):
            yf = old_yf
        if yf < 0.0:
            yf = 0.0
        if yf > 1.0:
            yf = 1.0
    e = target - yf
    if not math.isfinite(e):
        e = 0.0
    p = KP * e
    new_i = old_i
    ae = e if e >= 0.0 else -e
    if ae < E_EN:
        cand = old_i + KI * e * dtc
        if cand < I_MIN:
            cand = I_MIN
        if cand > I_MAX:
            cand = I_MAX
        u_test = ff + p + cand
        if u_test > U_MAX and e > 0.0:
            new_i = old_i
        elif u_test < U_MIN and e < 0.0:
            new_i = old_i
        else:
            new_i = cand
    else:
        new_i = old_i
    u = ff + p + new_i
    if not math.isfinite(u):
        u = ff
    if u > U_MAX:
        u = U_MAX
    if u < U_MIN:
        u = U_MIN
    if u > 1.0:
        u = 1.0
    if u < 0.0:
        u = 0.0
    ns = {"yf": float(yf), "i": float(new_i)}
    return (float(u), ns)
