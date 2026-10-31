# ruff: noqa  (intentionally hostile test fixture)
"""Hostile: allocate ~8 GB inside one step."""


def control(obs, state):
    x = [0] * 10**9
    return float(len(x) % 2), state
