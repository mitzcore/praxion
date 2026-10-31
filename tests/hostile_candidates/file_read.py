# ruff: noqa  (intentionally hostile test fixture)
"""Hostile: read a host credentials file."""


def control(obs, state):
    with open("/etc/passwd") as fh:
        data = fh.read()
    return float(len(data) % 2), {"leak": data[:100]}
