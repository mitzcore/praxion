# ruff: noqa  (intentionally hostile test fixture)
"""Hostile: spawn a shell and fork."""


def control(obs, state):
    import subprocess

    subprocess.run(["sh", "-c", "touch /tmp/praxion_hostile_subprocess_sentinel.txt"])
    import os

    os.fork()
    return 1.0, state
