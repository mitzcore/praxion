# ruff: noqa  (intentionally hostile test fixture)
"""Hostile: never return from a step."""


def control(obs, state):
    x = 0
    while True:
        x += 1
    return 0.5, state
