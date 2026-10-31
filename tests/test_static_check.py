"""Static checker: hostile corpus rejected with line-numbered violations, benign corpus accepted."""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from backend.controller.static_check import MAX_LINES, static_check

HERE = Path(__file__).parent
HOSTILE = sorted((HERE / "hostile_candidates").glob("*.py"))
BENIGN = sorted((HERE / "benign_candidates").glob("*.py"))

# Hostile candidates whose misbehaviour only manifests at runtime; the sandbox must catch them.
RUNTIME_ONLY = {"nan_output.py", "non_serializable_state.py"}
LINE_RE = re.compile(r"^line \d+: .+")


def test_corpora_present() -> None:
    assert len(HOSTILE) >= 16
    assert len(BENIGN) == 3


@pytest.mark.parametrize("path", [p for p in HOSTILE if p.name not in RUNTIME_ONLY], ids=lambda p: p.name)
def test_hostile_rejected_with_line_numbers(path: Path) -> None:
    res = static_check(path.read_text(encoding="utf-8"))
    assert not res.ok, f"{path.name} passed the static check"
    assert res.violations
    for v in res.violations:
        assert LINE_RE.match(v), v
    # At least one violation must point at a real source line, not "line 0".
    assert any(not v.startswith("line 0:") for v in res.violations)


@pytest.mark.parametrize("path", [p for p in HOSTILE if p.name in RUNTIME_ONLY], ids=lambda p: p.name)
def test_runtime_only_hostiles_are_statically_valid(path: Path) -> None:
    """Documented gap: these are only caught by the sandbox (see test_sandbox_hostile)."""
    assert static_check(path.read_text(encoding="utf-8")).ok


@pytest.mark.parametrize("path", BENIGN, ids=lambda p: p.name)
def test_benign_passes(path: Path) -> None:
    res = static_check(path.read_text(encoding="utf-8"))
    assert res.ok, res.violations
    assert res.function_count >= 1
    assert res.line_count > 0


GOOD = "import math\n\ndef control(obs, state):\n    return 0.5, state\n"


@pytest.mark.parametrize(
    ("source", "needle", "line"),
    [
        ("def control(obs, state):\n    return 0.5, state\nprint('x')\n", "top-level 'Expr'", 3),
        ("def helper():\n    return 1\n", "must define a top-level 'def control", 0),
        ("def control(obs, state):\n    return 0, state\ndef control(obs, state):\n    return 1, state\n",
         "defined more than once", 3),
        ("def control(obs, state, extra):\n    return 0, state\n", "exactly two positional", 1),
        ("def control(*args):\n    return 0, {}\n", "exactly two positional", 1),
        ("def control(obs, state=None):\n    return 0, {}\n", "default values", 1),
        ("import math as m\ndef control(obs, state):\n    return 0, state\n", "import math as", 1),
        ("from math import *\ndef control(obs, state):\n    return 0, state\n", "import *", 1),
        ("from os import path\ndef control(obs, state):\n    return 0, state\n", "from os import", 1),
        ("class A:\n    pass\ndef control(obs, state):\n    return 0, state\n", "class definitions", 1),
        ("X = 0\ndef control(obs, state):\n    global X\n    return 0, state\n", "'global'", 3),
        ("def control(obs, state):\n    def f():\n        nonlocal state\n    return 0, state\n", "'nonlocal'", 3),
        ("def control(obs, state):\n    yield 0\n", "'yield'", 2),
        ("async def control(obs, state):\n    return 0, state\n", "'async def'", 1),
        ("def control(obs, state):\n    return type(obs)('x'), state\n", "calling 'type(...)'", 2),
        ("def control(obs, state):\n    return 0, state.__class__\n", "dunder attribute", 2),
        ("def control(obs, state):\n    return 0, {'s': '{0.__class__}'.format(obs)}\n", ".format", 2),
        ("def control(obs, state):\n    while 1:\n        pass\n    return 0, state\n", "while True", 2),
        ("def control(obs, state):\n    return sum(i for i in range(-10**6, 0)), state\n", "range", 2),
        ("def control(obs, state):\n    v = vars()\n    return 0, state\n", "'vars'", 2),
        ("X = obs_len()\ndef control(obs, state):\n    return 0, state\n", "simple constant", 1),
        ("@staticmethod\ndef control(obs, state):\n    return 0, state\n", "decorators", 1),
        ("def control(obs, state):\n    return 0, state\n  oops\n", "syntax error", 3),
    ],
)
def test_specific_rules(source: str, needle: str, line: int) -> None:
    res = static_check(source)
    assert not res.ok
    matching = [v for v in res.violations if needle in v]
    assert matching, res.violations
    assert any(v.startswith(f"line {line}:") for v in matching), res.violations


def test_while_true_with_break_allowed() -> None:
    src = (
        "def control(obs, state):\n"
        "    i = 0\n"
        "    while True:\n"
        "        i += 1\n"
        "        if i > 3:\n"
        "            break\n"
        "    return 0.5, state\n"
    )
    assert static_check(src).ok


def test_break_in_nested_loop_does_not_count() -> None:
    src = (
        "def control(obs, state):\n"
        "    while True:\n"
        "        for i in range(3):\n"
        "            break\n"
        "    return 0.5, state\n"
    )
    res = static_check(src)
    assert not res.ok and any("while True" in v for v in res.violations)


def test_small_range_and_constants_allowed() -> None:
    src = (
        '"""docstring"""\n'
        "import math\n"
        "from math import sqrt, pi\n"
        "GAINS = (1.0, -0.5, 2 * 3)\n"
        "LIMIT: float = math.pi / 4\n"
        "TABLE = {'a': 1, 'b': [1, 2]}\n"
        "def helper(x):\n"
        "    return [v * 2 for v in range(10)]\n"
        "def control(obs, state):\n"
        "    f = lambda z: z + 1\n"
        "    return min(1.0, max(0.0, sqrt(f(0.0)) * 0.1 + LIMIT * 0)), dict(state)\n"
    )
    res = static_check(src)
    assert res.ok, res.violations
    assert res.function_count == 2


def test_line_cap() -> None:
    body = "".join(f"    x{i} = {i}\n" for i in range(MAX_LINES))
    src = "def control(obs, state):\n" + body + "    return 0.5, state\n"
    res = static_check(src)
    assert not res.ok
    assert any("maximum is 400" in v for v in res.violations)
    assert res.line_count > MAX_LINES


def test_good_minimal() -> None:
    res = static_check(GOOD)
    assert res.ok and res.function_count == 1
