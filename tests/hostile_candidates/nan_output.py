# ruff: noqa  (intentionally hostile test fixture)
"""Hostile: request a NaN actuator command."""


def control(obs, state):
    return float("nan"), state
