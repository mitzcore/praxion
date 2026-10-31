# ruff: noqa  (intentionally hostile test fixture)
"""Hostile: return state that cannot round-trip through JSON (a set and a function)."""


def control(obs, state):
    return 0.5, {"seen": {1, 2, 3}, "fn": control}
