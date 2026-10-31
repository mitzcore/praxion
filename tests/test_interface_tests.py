"""Interface tests: run against benign/hostile candidates in the dev subprocess sandbox,
against pure in-process fakes (to test the checker logic), and under Docker."""
from __future__ import annotations

import itertools
from pathlib import Path

import pytest

from backend.controller.interface_tests import run_interface_tests
from backend.controller.sandbox import (
    DEFAULT_IMAGE,
    DockerSandboxController,
    SubprocessDevSandboxController,
    docker_available,
    ensure_image,
)

HERE = Path(__file__).parent
BENIGN = sorted((HERE / "benign_candidates").glob("*.py"))
EXPECTED_CHECKS = ["cold_start", "sequence_50", "nan_y", "inf_y", "zero_dt", "negative_dt", "determinism",
                   "timing"]


def _src(rel: str) -> str:
    return (HERE / rel).read_text(encoding="utf-8")


def _dev(source: str, **kw):
    return lambda: SubprocessDevSandboxController(source, "it", **kw)


@pytest.mark.parametrize("path", BENIGN, ids=lambda p: p.name)
def test_benign_pass_dev_subprocess(path: Path) -> None:
    rep = run_interface_tests(_dev(path.read_text(encoding="utf-8")))
    assert [c.name for c in rep.checks] == EXPECTED_CHECKS
    assert rep.ok, rep.failures()


def test_nan_output_fails_cold_start_dev() -> None:
    rep = run_interface_tests(_dev(_src("hostile_candidates/nan_output.py")))
    assert not rep.ok
    by = {c.name: c for c in rep.checks}
    assert not by["cold_start"].ok and "must be finite" in by["cold_start"].detail
    assert by["determinism"].ok  # NaN, NaN, ... is still deterministic


def test_non_serializable_state_fails_dev() -> None:
    rep = run_interface_tests(_dev(_src("hostile_candidates/non_serializable_state.py")))
    assert not rep.ok
    assert "JSON-serializable" in {c.name: c for c in rep.checks}["cold_start"].detail


def test_load_error_reported_on_every_check_dev() -> None:
    rep = run_interface_tests(_dev("def control(obs):\n  return (\n"))
    assert not rep.ok
    assert all(not c.ok and "SandboxLoadError" in c.detail for c in rep.checks)


def test_timeout_reported_not_raised_dev() -> None:
    rep = run_interface_tests(_dev(_src("hostile_candidates/infinite_loop.py"), step_timeout_s=0.5))
    assert not rep.ok
    assert all("SandboxTimeout" in c.detail for c in rep.checks)


def test_nan_y_crash_vs_reported() -> None:
    """A controller that errors on NaN y is fine; one that never recovers is not."""
    src_raises = (
        "import math\n"
        "def control(obs, state):\n"
        "    if not math.isfinite(obs['y']):\n"
        "        raise ValueError('bad y')\n"
        "    return 0.5, state\n"
    )
    rep = run_interface_tests(_dev(src_raises))
    by = {c.name: c for c in rep.checks}
    assert by["nan_y"].ok and "bad y" in by["nan_y"].detail
    # Poisoned state: after a NaN y, the controller returns NaN forever -> fail.
    src_poison = (
        "def control(obs, state):\n"
        "    if obs['y'] != obs['y']:\n"
        "        return 0.0, {'dead': True}\n"
        "    if state.get('dead'):\n"
        "        return float('nan'), state\n"
        "    return 0.5, state\n"
    )
    rep = run_interface_tests(_dev(src_poison))
    assert not {c.name: c for c in rep.checks}["nan_y"].ok


class _Fake:
    """In-process trusted fake used only to exercise the checker logic."""

    isolation = "trusted"

    def __init__(self, fn) -> None:
        self.name = "fake"
        self.fn = fn

    def reset(self) -> None:
        pass

    def step(self, obs: dict) -> float:
        return self.fn(obs)

    def close(self) -> None:
        pass


def test_nondeterminism_detected() -> None:
    counter = itertools.count()
    rep = run_interface_tests(lambda: _Fake(lambda obs: (next(counter) % 7) / 10.0))
    by = {c.name: c for c in rep.checks}
    assert not by["determinism"].ok and "differ" in by["determinism"].detail


def test_out_of_range_cold_start_detected() -> None:
    rep = run_interface_tests(lambda: _Fake(lambda obs: 1.5))
    assert not {c.name: c for c in rep.checks}["cold_start"].ok


def test_slow_controller_fails_timing(monkeypatch: pytest.MonkeyPatch) -> None:
    import backend.controller.interface_tests as it

    monkeypatch.setattr(it, "TIMING_BUDGET_S", 0.0)
    rep = run_interface_tests(lambda: _Fake(lambda obs: 0.5))
    assert not {c.name: c for c in rep.checks}["timing"].ok


@pytest.mark.docker
def test_benign_pass_docker() -> None:
    if not docker_available():
        pytest.skip("Docker daemon not reachable (docker info failed)")
    ensure_image(DEFAULT_IMAGE)
    src = _src("benign_candidates/pi_controller.py")
    rep = run_interface_tests(lambda: DockerSandboxController(src, "it-docker"))
    print("\n" + "\n".join(f"{c.name}: {c.ok} {c.detail}" for c in rep.checks))
    assert rep.ok, rep.failures()
    assert "budget 10s" in {c.name: c for c in rep.checks}["timing"].detail
