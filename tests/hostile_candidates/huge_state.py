# ruff: noqa  (intentionally hostile test fixture)
"""Hostile: return a 50 MB string in the state dict (memory / IPC exhaustion)."""


def control(obs, state):
    return 0.5, {"blob": "x" * 50_000_000}
