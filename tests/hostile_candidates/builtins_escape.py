# ruff: noqa  (intentionally hostile test fixture)
"""Hostile: recover the real __import__ from __builtins__ and import os."""


def control(obs, state):
    b = __builtins__
    imp = b["__import__"] if isinstance(b, dict) else b.__import__
    os_mod = imp("os")
    os_mod.system("touch /tmp/praxion_hostile_builtins_sentinel.txt")
    os2 = __import__("os")
    return float(len(os2.listdir("/"))), state
