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
    KI_NEAR = 0.035
    KI_FAR = 0.005
    E_NEAR = 0.20
    TF = 15.0
    CLIP = 0.045
    I_MIN = -0.30
    I_MAX = 0.70
    FF_MIN = 0.05
    FF_MAX = 0.85
    U_MIN = 0.0
    U_MAX = 0.95
    T_TRANS = 120.0
    E_TRANS = 0.04
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
    try:
        old_ff = float(state.get("ff", 0.26))
        if not math.isfinite(old_ff):
            old_ff = 0.26
    except Exception:
        old_ff = 0.26
    if old_yf < 0.0:
        old_yf = 0.0
    if old_yf > 1.0:
        old_yf = 1.0
    if old_i < I_MIN:
        old_i = I_MIN
    if old_i > I_MAX:
        old_i = I_MAX
    if old_ff < FF_MIN:
        old_ff = FF_MIN
    if old_ff > FF_MAX:
        old_ff = FF_MAX
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
    ae = e if e >= 0.0 else -e
    ki = KI_NEAR if ae < E_NEAR else KI_FAR
    p = KP * e
    cand_i = old_i + ki * e * dtc
    if cand_i < I_MIN:
        cand_i = I_MIN
    if cand_i > I_MAX:
        cand_i = I_MAX
    ff_use_base = old_ff + (target - 0.5)
    if ff_use_base < FF_MIN:
        ff_use_base = FF_MIN
    if ff_use_base > FF_MAX:
        ff_use_base = FF_MAX
    u_test = ff_use_base + p + cand_i
    new_i = old_i
    if u_test > U_MAX and e > 0.0:
        new_i = old_i
    elif u_test < U_MIN and e < 0.0:
        new_i = old_i
    else:
        new_i = cand_i
    new_ff = old_ff
    if ae < E_TRANS:
        delta = new_i * dtc / T_TRANS
        if delta > 0.02:
            delta = 0.02
        if delta < -0.02:
            delta = -0.02
        tmp_ff = new_ff + delta
        if tmp_ff < FF_MIN:
            tmp_ff = FF_MIN
        if tmp_ff > FF_MAX:
            tmp_ff = FF_MAX
        shift = tmp_ff - new_ff
        new_ff = tmp_ff
        new_i = new_i - shift
        if new_i < I_MIN:
            new_i = I_MIN
        if new_i > I_MAX:
            new_i = I_MAX
    ff_use = new_ff + (target - 0.5)
    if ff_use < FF_MIN:
        ff_use = FF_MIN
    if ff_use > FF_MAX:
        ff_use = FF_MAX
    u = ff_use + p + new_i
    if not math.isfinite(u):
        u = ff_use
    if u > U_MAX:
        u = U_MAX
    if u < U_MIN:
        u = U_MIN
    if yf >= 0.84:
        if u > 0.15:
            u = 0.15
    elif yf >= 0.80:
        if u > 0.40:
            u = 0.40
    if u > 1.0:
        u = 1.0
    if u < 0.0:
        u = 0.0
    ns = {"yf": float(yf), "i": float(new_i), "ff": float(new_ff)}
    return (float(u), ns)
