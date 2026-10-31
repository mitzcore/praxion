"""Sandbox interface tests: behavioural contract checks run on a candidate before scoring.

Each check builds a *fresh* controller from ``factory`` (so one failure cannot leak into
the next), calls ``reset()``, exercises it, and always ``close()``s it. Results are
reported per check with a human-readable ``detail`` that can be fed back to Muse.
"""
from __future__ import annotations

import math
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager

from pydantic import BaseModel

from backend.controller.protocol import Controller

TIMING_STEPS = 200
TIMING_BUDGET_S = 10.0
DETERMINISM_STEPS = 30
SEQUENCE_STEPS = 50


class InterfaceCheck(BaseModel):
    """One named check."""

    name: str
    ok: bool
    detail: str


class InterfaceReport(BaseModel):
    """All checks; ``ok`` only if every check passed."""

    ok: bool
    checks: list[InterfaceCheck]

    def failures(self) -> list[InterfaceCheck]:
        """Checks that did not pass."""
        return [c for c in self.checks if not c.ok]


def _obs(y: float, *, target: float = 0.5, dt: float = 0.1, elapsed_s: float = 0.0) -> dict:
    return {"y": y, "target": target, "dt": dt, "elapsed_s": elapsed_s}


def _finite(u: object) -> bool:
    return isinstance(u, (int, float)) and not isinstance(u, bool) and math.isfinite(u)


def _err(c: Controller) -> str:
    e = getattr(c, "last_error", None)
    return f" (last_error: {e})" if e else ""


@contextmanager
def _fresh(factory: Callable[[], Controller]) -> Iterator[Controller]:
    c = factory()
    try:
        c.reset()
        yield c
    finally:
        try:
            c.close()
        except Exception:  # noqa: BLE001, S110 - a failing close must not mask the check result
            pass


def _check_cold_start(c: Controller) -> tuple[bool, str]:
    u = c.step(_obs(0.2))
    if not _finite(u):
        return False, f"first step with empty state returned {u!r}{_err(c)}"
    if not 0.0 <= u <= 1.0:
        return False, f"first step returned u={u!r}, outside [0, 1]"
    return True, f"u={u:.6g}"


def _check_sequence(c: Controller) -> tuple[bool, str]:
    for i in range(SEQUENCE_STEPS):
        y = 0.3 + 0.2 * math.sin(i / 10.0)
        u = c.step(_obs(y, elapsed_s=0.1 * i))
        if not _finite(u):
            return False, f"step {i} (y={y:.4f}) returned {u!r}{_err(c)}"
    return True, f"{SEQUENCE_STEPS} consecutive steps returned finite u"


def _survives(c: Controller, bad_obs: dict, label: str) -> tuple[bool, str]:
    """Bad input may yield NaN/error, but the sandbox must stay alive and keep working."""
    u = c.step(bad_obs)
    what = f"returned finite u={u:.6g}" if _finite(u) else f"returned {u!r}{_err(c)} (reported)"
    u2 = c.step(_obs(0.3, elapsed_s=1.0))
    if not _finite(u2):
        return False, f"{label}: {what}; the following valid step returned {u2!r}{_err(c)}"
    return True, f"{label}: {what}; process alive, next valid step u={u2:.6g}"


def _check_nan_y(c: Controller) -> tuple[bool, str]:
    return _survives(c, _obs(float("nan")), "y=NaN")


def _check_inf_y(c: Controller) -> tuple[bool, str]:
    return _survives(c, _obs(float("inf")), "y=+inf")


def _check_zero_dt(c: Controller) -> tuple[bool, str]:
    return _survives(c, _obs(0.3, dt=0.0), "dt=0")


def _check_negative_dt(c: Controller) -> tuple[bool, str]:
    return _survives(c, _obs(0.3, dt=-0.1), "dt=-0.1")


def _determinism_obs() -> list[dict]:
    return [_obs(0.1 + 0.6 * ((i * 7) % 13) / 13.0, elapsed_s=0.1 * i) for i in range(DETERMINISM_STEPS)]


def _same(a: float, b: float) -> bool:
    return (math.isnan(a) and math.isnan(b)) or a == b


class _Runner:
    def __init__(self, factory: Callable[[], Controller]) -> None:
        self.factory = factory
        self.checks: list[InterfaceCheck] = []

    def run(self, name: str, fn: Callable[[Controller], tuple[bool, str]]) -> None:
        try:
            with _fresh(self.factory) as c:
                ok, detail = fn(c)
        except Exception as exc:  # noqa: BLE001 - load errors, timeouts, crashes all fail the check
            ok, detail = False, f"{type(exc).__name__}: {exc}"[:800]
        self.checks.append(InterfaceCheck(name=name, ok=ok, detail=detail))

    def run_determinism(self) -> None:
        seqs: list[list[float]] = []
        try:
            for _ in range(2):
                with _fresh(self.factory) as c:
                    seqs.append([float(c.step(o)) for o in _determinism_obs()])
            diffs = [i for i, (a, b) in enumerate(zip(seqs[0], seqs[1], strict=True)) if not _same(a, b)]
            if diffs:
                i = diffs[0]
                ok, detail = False, f"sequences differ at step {i}: {seqs[0][i]!r} vs {seqs[1][i]!r}"
            else:
                ok, detail = True, f"two fresh controllers produced identical {DETERMINISM_STEPS}-step sequences"
        except Exception as exc:  # noqa: BLE001
            ok, detail = False, f"{type(exc).__name__}: {exc}"[:800]
        self.checks.append(InterfaceCheck(name="determinism", ok=ok, detail=detail))

    def run_timing(self) -> None:
        def fn(c: Controller) -> tuple[bool, str]:
            t0 = time.monotonic()
            for i in range(TIMING_STEPS):
                c.step(_obs(0.3 + 0.001 * i, elapsed_s=0.1 * i))
            dt = time.monotonic() - t0
            ok = dt < TIMING_BUDGET_S
            return ok, f"{TIMING_STEPS} steps in {dt:.3f}s (budget {TIMING_BUDGET_S:.0f}s)"

        self.run("timing", fn)


def run_interface_tests(factory: Callable[[], Controller]) -> InterfaceReport:
    """Run all interface checks against controllers produced by ``factory``."""
    r = _Runner(factory)
    r.run("cold_start", _check_cold_start)
    r.run("sequence_50", _check_sequence)
    r.run("nan_y", _check_nan_y)
    r.run("inf_y", _check_inf_y)
    r.run("zero_dt", _check_zero_dt)
    r.run("negative_dt", _check_negative_dt)
    r.run_determinism()
    r.run_timing()
    return InterfaceReport(ok=all(c.ok for c in r.checks), checks=r.checks)
