# ruff: noqa  (intentionally hostile test fixture)
"""Hostile: write a file (the host must never see it)."""


def control(obs, state):
    with open("/tmp/praxion_hostile_write_sentinel.txt", "w") as fh:
        fh.write("pwned")
    return 1.0, state
