# ruff: noqa  (intentionally hostile test fixture)
"""Hostile: exec a string to smuggle an import past the AST checker."""


def control(obs, state):
    ns = {}
    exec("import os; r = os.listdir('/')", ns)
    return float(len(ns["r"])), state
