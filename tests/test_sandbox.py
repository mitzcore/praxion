"""Docker sandbox: benign operation, wall-clock timeout, CPU rlimit, container cleanup."""
from __future__ import annotations

import subprocess
import time
from pathlib import Path

import pytest

from backend.controller.protocol import Controller
from backend.controller.sandbox import (
    DEFAULT_IMAGE,
    DockerSandboxController,
    SandboxCrashed,
    SandboxLoadError,
    SandboxTimeout,
    docker_available,
    ensure_image,
    make_sandbox,
)

pytestmark = pytest.mark.docker

HERE = Path(__file__).parent
PI = (HERE / "benign_candidates" / "pi_controller.py").read_text(encoding="utf-8")
CPU_BURN = (HERE / "hostile_candidates" / "cpu_burn.py").read_text(encoding="utf-8")


@pytest.fixture(scope="module", autouse=True)
def _docker() -> None:
    if not docker_available():
        pytest.skip("Docker daemon not reachable (docker info failed)")
    ensure_image(DEFAULT_IMAGE)


def _running(filter_: str) -> set[str]:
    out = subprocess.run(["docker", "ps", "-q", "--filter", filter_], capture_output=True, text=True,
                         timeout=30, check=True).stdout
    return set(out.split())


def _obs(y: float, i: int = 0, dt: float = 0.1) -> dict:
    return {"y": y, "target": 0.5, "dt": dt, "elapsed_s": i * dt}


def test_benign_pi_100_steps_state_roundtrip() -> None:
    c = DockerSandboxController(PI, "pi")
    assert isinstance(c, Controller)
    assert c.isolation == "docker"
    try:
        c.reset()
        y = 0.1
        us = []
        for i in range(100):
            u = c.step(_obs(y, i))
            us.append(u)
            y += 0.05 * (u - 0.3) * 0.1  # crude plant, only to vary y
        assert all(0.0 <= u <= 1.0 for u in us)
        assert c.state["steps"] == 100
        assert isinstance(c.state["integral"], float)
        assert c.step_count == 100 and c.error_count == 0 and c.last_error is None
        # reset() restarts the container and clears host-owned state.
        c.reset()
        assert c.state == {}
        c.step(_obs(0.2))
        assert c.state["steps"] == 1
    finally:
        c.close()


def test_step_timeout_enforced_and_sandbox_stays_dead() -> None:
    c = DockerSandboxController(CPU_BURN, "burn", step_timeout_s=1.0)
    try:
        c.reset()
        name = c.container_name
        t0 = time.monotonic()
        with pytest.raises(SandboxTimeout):
            c.step(_obs(0.2))
        elapsed = time.monotonic() - t0
        assert elapsed < 3.0, f"timeout took {elapsed:.2f}s"
        assert not _running(f"name={name}"), "container still running after timeout"
        with pytest.raises(SandboxCrashed):
            c.step(_obs(0.2))  # no silent restart after a kill
    finally:
        c.close()


def test_cpu_rlimit_kills_runaway_even_without_wallclock() -> None:
    """Defense in depth: RLIMIT_CPU inside the container ends a burn the host did not time out."""
    c = DockerSandboxController(CPU_BURN, "burn-rlimit", step_timeout_s=30.0, total_cpu_s=2.0)
    try:
        c.reset()
        t0 = time.monotonic()
        with pytest.raises(SandboxCrashed):
            c.step(_obs(0.2))
        assert time.monotonic() - t0 < 15.0
    finally:
        c.close()


def test_close_leaves_no_container() -> None:
    before = _running(f"ancestor={DEFAULT_IMAGE}")
    c = DockerSandboxController(PI, "pi-close")
    c.reset()
    name = c.container_name
    assert _running(f"name={name}"), "container should be running while in use"
    c.step(_obs(0.2))
    c.close()
    c.close()  # idempotent
    after = _running(f"ancestor={DEFAULT_IMAGE}")
    assert after <= before, f"leftover containers: {after - before}"
    assert not _running(f"name={name}")


def test_del_cleans_up() -> None:
    c = DockerSandboxController(PI, "pi-del")
    c.reset()
    name = c.container_name
    del c
    import gc

    gc.collect()
    deadline = time.monotonic() + 10
    while _running(f"name={name}") and time.monotonic() < deadline:
        time.sleep(0.2)
    assert not _running(f"name={name}")


def test_load_errors() -> None:
    for src, needle in [
        ("def control(obs, state):\n  return (\n", "SyntaxError"),
        ("x = 1\n", "control"),
        ("import os\ndef control(obs, state):\n    return 0, state\n", "ImportError"),
    ]:
        c = DockerSandboxController(src, "bad")
        with pytest.raises(SandboxLoadError, match=needle):
            c.reset()
        c.close()


def test_make_sandbox_modes() -> None:
    c = make_sandbox(PI, "pi-factory", "docker")
    assert c.isolation == "docker"
    c.close()
    d = make_sandbox(PI, "pi-dev", "subprocess_dev_only")
    assert d.isolation == "subprocess_dev_only"
    d.close()
    with pytest.raises(ValueError):
        make_sandbox(PI, "x", "inprocess")
