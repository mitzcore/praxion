# ruff: noqa  (intentionally hostile test fixture)
"""Hostile: import os and enumerate the filesystem."""
import os


def control(obs, state):
    return float(len(os.listdir("/"))), state
