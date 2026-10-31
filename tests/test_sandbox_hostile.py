"""Every hostile candidate, loaded straight into the Docker sandbox with NO static check.

Allowed outcomes: load error, step error, NaN rejected, SandboxTimeout, sandbox killed.
A finite u means the attack ran to completion and the test fails. Separately, the
container layer itself is probed with *unrestricted* Python (no runner, no restricted
builtins, no audit hook) to show the network and filesystem are blocked even if every
in-process layer were bypassed.
"""
from __future__ import annotations

import json
import math
import subprocess
import sys
import time
import uuid
from pathlib import Path

import pytest

from backend.controller.sandbox import (
    DEFAULT_IMAGE,
    DockerSandboxController,
    SandboxCrashed,
    SandboxLoadError,
    SandboxTimeout,
    docker_available,
    docker_run_args,
    ensure_image,
)

pytestmark = pytest.mark.docker

HERE = Path(__file__).parent
HOSTILE = sorted((HERE / "hostile_candidates").glob("*.py"))
SENTINELS = [
    Path("/tmp/praxion_hostile_write_sentinel.txt"),
    Path("/tmp/praxion_hostile_subprocess_sentinel.txt"),
    Path("/tmp/praxion_hostile_dunder_sentinel.txt"),
    Path("/tmp/praxion_hostile_builtins_sentinel.txt"),
]
ALLOWED = {"load_error", "step_error", "nan_rejected", "timeout", "killed"}
OBS = {"y": 0.2, "target": 0.5, "dt": 0.1, "elapsed_s": 0.0}

# Expected outcome per candidate (a set where the kernel may legitimately pick either path).
EXPECTED: dict[str, set[str]] = {
    "import_os.py": {"load_error"},
    "network.py": {"load_error"},
    "network_escape.py": {"step_error"},
    "file_read.py": {"step_error"},
    "file_write.py": {"step_error"},
    "subprocess_fork.py": {"step_error"},
    "dunder_escape.py": {"step_error"},
    "builtins_escape.py": {"step_error"},
    "frame_escape.py": {"step_error"},
    "infinite_loop.py": {"timeout"},
    "memory_bomb.py": {"step_error", "killed"},
    "cpu_burn.py": {"timeout"},
    "exec_string.py": {"step_error"},
    "getattr_escape.py": {"step_error"},
    "huge_state.py": {"step_error", "killed"},
    "non_serializable_state.py": {"step_error"},
    "nan_output.py": {"nan_rejected"},
    "wrong_signature.py": {"step_error"},
}


@pytest.fixture(scope="module", autouse=True)
def _docker() -> None:
    if not docker_available():
        pytest.skip("Docker daemon not reachable (docker info failed)")
    ensure_image(DEFAULT_IMAGE)
    for s in SENTINELS:
        s.unlink(missing_ok=True)


def _host_responsive() -> None:
    t0 = time.monotonic()
    subprocess.run([sys.executable, "-c", "pass"], check=True, timeout=10)
    assert time.monotonic() - t0 < 10


def _running(filter_: str) -> set[str]:
    out = subprocess.run(["docker", "ps", "-q", "--filter", filter_], capture_output=True, text=True,
                         timeout=30, check=True).stdout
    return set(out.split())


def classify(c: DockerSandboxController, steps: int = 3) -> tuple[str, str]:
    """Run a candidate and map what happened onto an outcome label."""
    try:
        c.reset()
    except SandboxLoadError as exc:
        return "load_error", str(exc)
    except SandboxTimeout as exc:
        return "timeout", str(exc)
    for _ in range(steps):
        try:
            u = c.step(dict(OBS))
        except SandboxTimeout as exc:
            return "timeout", str(exc)
        except SandboxCrashed as exc:
            return "killed", str(exc)
        if math.isnan(u):
            err = c.last_error or ""
            return ("nan_rejected" if "must be finite" in err else "step_error"), err
        if math.isfinite(u):
            return "finite", f"u={u!r} state={json.dumps(c.state)[:200]}"
    return "finite", "?"


def test_corpus_complete() -> None:
    assert {p.name for p in HOSTILE} == set(EXPECTED)


@pytest.mark.parametrize("path", HOSTILE, ids=lambda p: p.name)
def test_hostile_contained(path: Path) -> None:
    c = DockerSandboxController(path.read_text(encoding="utf-8"), path.stem, step_timeout_s=2.0)
    try:
        t0 = time.monotonic()
        outcome, detail = classify(c)
        elapsed = time.monotonic() - t0
        name = c.container_name
    finally:
        c.close()
    print(f"\nHOSTILE {path.name}: {outcome} in {elapsed:.2f}s :: {detail[:300]}")
    assert outcome in ALLOWED, f"{path.name} was not contained: {outcome}: {detail}"
    assert outcome in EXPECTED[path.name], f"{path.name}: {outcome}: {detail}"
    if path.name.startswith("network"):
        assert "socket" in detail or "not permitted" in detail, detail
    for s in SENTINELS:
        assert not s.exists(), f"{path.name} created host file {s}"
    if name is not None:
        assert not _running(f"name={name}")
    _host_responsive()


PROBE = r'''
import json, os, socket
r = {"uid": os.getuid(), "gid": os.getgid()}
def attempt(key, fn):
    try:
        fn(); r[key] = "SUCCEEDED"
    except Exception as e:
        r[key] = type(e).__name__ + ": " + str(e)[:120]
attempt("tcp_1.1.1.1:53", lambda: socket.create_connection(("1.1.1.1", 53), timeout=2).close())
attempt("tcp_8.8.8.8:443", lambda: socket.create_connection(("8.8.8.8", 443), timeout=2).close())
attempt("dns_example.com", lambda: socket.getaddrinfo("example.com", 80))
attempt("dns_host.docker.internal", lambda: socket.getaddrinfo("host.docker.internal", 80))
attempt("udp_send", lambda: socket.socket(socket.AF_INET, socket.SOCK_DGRAM).sendto(b"x", ("1.1.1.1", 53)))
r["interfaces"] = sorted(os.listdir("/sys/class/net"))
r["up_interfaces"] = sorted(i for i in os.listdir("/sys/class/net")
                            if int(open(f"/sys/class/net/{i}/flags").read(), 16) & 0x1)
attempt("write_root", lambda: open("/praxion_probe", "w").write("x"))
attempt("write_etc", lambda: open("/etc/praxion_probe", "w").write("x"))
attempt("write_usr", lambda: open("/usr/praxion_probe", "w").write("x"))
attempt("write_tmp", lambda: open("/tmp/praxion_probe", "w").write("x"))
def exec_tmp():
    with open("/tmp/praxion_exec.sh", "w") as fh:
        fh.write("#!/bin/sh\necho hi\n")
    os.chmod("/tmp/praxion_exec.sh", 0o755)
    os.execv("/tmp/praxion_exec.sh", ["/tmp/praxion_exec.sh"])
pid = os.fork()
if pid == 0:
    try:
        exec_tmp()
    finally:
        os._exit(3)
_, status = os.waitpid(pid, 0)
r["exec_from_tmp_exit"] = os.waitstatus_to_exitcode(status)
r["host_paths_visible"] = [p for p in ("/Users", "/home/mitz", "/var/run/docker.sock", "/root/.ssh")
                            if os.path.exists(p)]
attempt("setuid_0", lambda: os.setuid(0))
with open("/proc/self/status") as fh:
    r["cap_eff"] = [l.split()[1] for l in fh if l.startswith("CapEff")][0]
    fh.seek(0)
    r["no_new_privs"] = [l.split()[1] for l in fh if l.startswith("NoNewPrivs")][0]
print(json.dumps(r))
'''


def test_container_layer_blocks_network_and_host_fs_without_runner() -> None:
    """Unrestricted Python inside the same container flags: no network, no host FS, no privileges."""
    name = f"praxion-probe-{uuid.uuid4().hex[:12]}"
    cmd = docker_run_args(DEFAULT_IMAGE, container_name=name) + ["python", "-I", "-c", PROBE]
    p = subprocess.run(cmd, capture_output=True, text=True, timeout=60, check=False)
    assert p.returncode == 0, p.stderr
    r = json.loads(p.stdout.strip().splitlines()[-1])
    print("\nCONTAINER PROBE:", json.dumps(r, indent=1))
    assert (r["uid"], r["gid"]) == (65534, 65534)
    for key in ("tcp_1.1.1.1:53", "tcp_8.8.8.8:443", "dns_example.com", "dns_host.docker.internal", "udp_send"):
        assert r[key] != "SUCCEEDED", f"network reachable: {key}"
    # tunl0/ip6tnl0 may exist as DOWN kernel placeholders in any netns; only loopback may be UP.
    assert r["up_interfaces"] == ["lo"], r["interfaces"]
    for key in ("write_root", "write_etc", "write_usr"):
        assert "Read-only file system" in r[key], (key, r[key])
    assert r["write_tmp"] == "SUCCEEDED"  # the 16 MB tmpfs is the only writable place...
    assert r["exec_from_tmp_exit"] != 0  # ...and it is noexec
    assert r["host_paths_visible"] == []
    assert r["setuid_0"] != "SUCCEEDED"
    assert int(r["cap_eff"], 16) == 0
    assert r["no_new_privs"] == "1"
    assert not Path("/tmp/praxion_probe").exists()  # the container's /tmp is not the host's
