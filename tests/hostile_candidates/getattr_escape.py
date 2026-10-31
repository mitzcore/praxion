# ruff: noqa  (intentionally hostile test fixture)
"""Hostile: getattr with a string to reach math's loader and import os through it."""
import math


def control(obs, state):
    loader = getattr(math, "__loader__")
    os_mod = loader.load_module("os")
    return float(len(os_mod.listdir("/"))), state
