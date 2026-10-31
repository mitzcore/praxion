# ruff: noqa  (intentionally hostile test fixture)
"""Hostile: wrong signature, control takes one argument."""


def control(obs):
    return 0.5, {}
