# ruff: noqa  (intentionally hostile test fixture)
"""Hostile: one step that burns ~10**9 loop iterations of CPU."""


def control(obs, state):
    acc = 0
    for i in range(10**9):
        acc += i
    return 0.5, {"acc": acc}
