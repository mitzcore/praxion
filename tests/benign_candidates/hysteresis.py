"""Benign: bang-bang controller with a hysteresis band."""

BAND = 0.02
U_ON = 0.9
U_OFF = 0.0


def control(obs, state):
    on = bool(state.get("on", False))
    y = obs["y"]
    target = obs["target"]
    if y < target - BAND:
        on = True
    elif y > target + BAND:
        on = False
    return (U_ON if on else U_OFF), {"on": on}
