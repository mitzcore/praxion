"""Host side of the untrusted-controller sandbox.

Model-authored controller code never runs in the host interpreter. It runs in a separate
process executing ``sandbox_runner.py`` and talks line-delimited JSON over stdio:

* :class:`DockerSandboxController` -- the real isolation boundary: a disposable
  ``python:3.12-slim`` container with no network, read-only rootfs, non-root user, all
  capabilities dropped, ``no-new-privileges``, memory/pids/cpu limits, and a host-enforced
  per-step wall-clock timeout.
* :class:`SubprocessDevSandboxController` -- **DEV ONLY, reduced isolation.** A plain
  ``python -I -S`` subprocess with the same runner (restricted builtins, audit hook,
  rlimits where the OS honours them) but *no* container: it can see the host filesystem
  and network if the in-process layers are bypassed. Never use it for a public demo,
  for scoring that is presented as sandboxed, or on hardware.

The host, not the sandbox, owns controller memory: the ``state`` dict returned by the
candidate is JSON round-tripped by the runner, stored here, and sent back on the next
step. A crashed or killed sandbox therefore cannot corrupt host state.
"""
from __future__ import annotations

import json
import math
import queue
import subprocess
import sys
import threading
import time
import uuid
from collections import deque
from pathlib import Path
from typing import Any

from backend.controller.protocol import Controller

RUNNER_PATH = Path(__file__).with_name("sandbox_runner.py")
RUNNER_SOURCE = RUNNER_PATH.read_text(encoding="utf-8")

DEFAULT_IMAGE = "python:3.12-slim"
CONTAINER_LABEL = "praxion.sandbox=1"
# Host-side cap on a single reply line (the runner caps state at 256 KiB).
MAX_REPLY_BYTES = 1024 * 1024


class SandboxError(RuntimeError):
    """Base class for sandbox failures."""


class SandboxLoadError(SandboxError):
    """The candidate could not be loaded (syntax/runtime error at import, no ``control``...)."""


class SandboxTimeout(SandboxError):
    """A step (or load) exceeded its wall-clock budget; the sandbox process was killed."""


class SandboxCrashed(SandboxError):
    """The sandbox process exited or broke the protocol (e.g. killed by the OOM killer or RLIMIT_CPU)."""


def docker_run_args(
    image: str = DEFAULT_IMAGE,
    *,
    container_name: str,
    memory: str = "256m",
    pids_limit: int = 64,
    cpus: str = "1",
) -> list[str]:
    """Return the locked-down ``docker run`` prefix (everything before the in-container command)."""
    return [
        "docker", "run", "-i", "--rm",
        "--name", container_name,
        "--label", CONTAINER_LABEL,
        "--network", "none",
        "--read-only",
        "--user", "65534:65534",
        "--cap-drop", "ALL",
        "--security-opt", "no-new-privileges",
        "--memory", memory,
        "--memory-swap", memory,
        "--pids-limit", str(pids_limit),
        "--cpus", cpus,
        "--tmpfs", "/tmp:rw,noexec,nosuid,size=16m",
        "--workdir", "/tmp",
        image,
    ]


def docker_available(timeout_s: float = 5.0) -> bool:
    """True if the Docker CLI exists and the daemon answers ``docker info`` within ``timeout_s``."""
    try:
        r = subprocess.run(["docker", "info"], capture_output=True, timeout=timeout_s, check=False)
    except (OSError, subprocess.TimeoutExpired):
        return False
    return r.returncode == 0


def ensure_image(image: str = DEFAULT_IMAGE, pull_timeout_s: float = 600.0) -> None:
    """Pull ``image`` if it is not present locally. Raises :class:`SandboxError` on failure."""
    r = subprocess.run(["docker", "image", "inspect", image], capture_output=True, timeout=30, check=False)
    if r.returncode == 0:
        return
    p = subprocess.run(["docker", "pull", image], capture_output=True, text=True, timeout=pull_timeout_s,
                       check=False)
    if p.returncode != 0:
        raise SandboxError(f"docker pull {image} failed: {p.stderr.strip()[-500:]}")


class _RunnerProcessController:
    """Shared machinery: spawn the runner, speak the protocol, enforce wall-clock budgets."""

    isolation: str = "abstract"

    def __init__(
        self,
        source: str,
        name: str,
        step_timeout_s: float = 2.0,
        total_cpu_s: float = 20.0,
        load_timeout_s: float = 30.0,
    ) -> None:
        self.source = source
        self.name = name
        self.step_timeout_s = float(step_timeout_s)
        self.total_cpu_s = float(total_cpu_s)
        self.load_timeout_s = float(load_timeout_s)
        self.state: dict[str, Any] = {}
        self.step_count = 0
        self.error_count = 0
        self.last_error: str | None = None
        self._proc: subprocess.Popen[bytes] | None = None
        self._lines: queue.Queue[bytes | None] = queue.Queue()
        self._stderr_tail: deque[str] = deque(maxlen=50)
        self._closed = False
        self._started = False

    # --- subclass hooks -----------------------------------------------------------------
    def _command(self) -> list[str]:
        raise NotImplementedError

    def _kill_backend(self) -> None:
        """Extra teardown after the local process is killed (e.g. ``docker kill``)."""

    # --- process management ---------------------------------------------------------------
    @property
    def alive(self) -> bool:
        """True while the runner process is running."""
        return self._proc is not None and self._proc.poll() is None

    def _spawn(self) -> None:
        self._lines = queue.Queue()
        self._stderr_tail = deque(maxlen=50)
        proc = subprocess.Popen(
            self._command(),
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=self._env(),
            close_fds=True,
        )
        self._proc = proc
        lines = self._lines
        tail = self._stderr_tail

        def read_stdout() -> None:
            assert proc.stdout is not None
            try:
                for raw in iter(lambda: proc.stdout.readline(MAX_REPLY_BYTES + 1), b""):
                    lines.put(raw)
            except (OSError, ValueError):
                pass
            lines.put(None)

        def read_stderr() -> None:
            assert proc.stderr is not None
            try:
                for raw in iter(lambda: proc.stderr.readline(8192), b""):
                    tail.append(raw.decode("utf-8", "replace").rstrip())
            except (OSError, ValueError):
                pass

        threading.Thread(target=read_stdout, name=f"sbx-out-{self.name}", daemon=True).start()
        threading.Thread(target=read_stderr, name=f"sbx-err-{self.name}", daemon=True).start()

    def _env(self) -> dict[str, str] | None:
        return None

    def _kill(self) -> None:
        proc = self._proc
        if proc is not None:
            try:
                if proc.poll() is None:
                    proc.kill()
                proc.wait(timeout=5)
            except (OSError, subprocess.TimeoutExpired):
                pass
            for stream in (proc.stdin, proc.stdout, proc.stderr):
                try:
                    if stream is not None:
                        stream.close()
                except OSError:
                    pass
        self._kill_backend()
        self._proc = None

    def _send(self, obj: dict[str, Any]) -> None:
        proc = self._proc
        if proc is None or proc.stdin is None:
            raise SandboxCrashed("sandbox process is not running")
        try:
            proc.stdin.write((json.dumps(obj) + "\n").encode("utf-8"))
            proc.stdin.flush()
        except (BrokenPipeError, OSError, ValueError) as exc:
            self._kill()
            raise SandboxCrashed(f"sandbox stdin closed: {exc}; stderr: {self.stderr_tail()}") from exc

    def _recv(self, timeout_s: float, what: str) -> dict[str, Any]:
        deadline = time.monotonic() + timeout_s
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                self._kill()
                self.last_error = f"SandboxTimeout: {what} exceeded {timeout_s:.2f}s"
                raise SandboxTimeout(f"{what} exceeded {timeout_s:.2f}s wall-clock budget; sandbox killed")
            try:
                raw = self._lines.get(timeout=remaining)
            except queue.Empty:
                continue
            if raw is None:
                code = self._proc.poll() if self._proc is not None else None
                self._kill()
                raise SandboxCrashed(
                    f"sandbox exited during {what} (exit code {code}); stderr: {self.stderr_tail()}"
                )
            if len(raw) > MAX_REPLY_BYTES:
                self._kill()
                raise SandboxCrashed(f"sandbox reply exceeded {MAX_REPLY_BYTES} bytes; sandbox killed")
            try:
                msg = json.loads(raw)
            except ValueError as exc:
                self._kill()
                raise SandboxCrashed(f"sandbox sent a malformed reply during {what}: {exc}") from exc
            if not isinstance(msg, dict):
                self._kill()
                raise SandboxCrashed(f"sandbox sent a non-object reply during {what}")
            return msg

    def stderr_tail(self, n: int = 10) -> str:
        """Last ``n`` lines the sandbox wrote to stderr (diagnostics only; untrusted text)."""
        return " | ".join(list(self._stderr_tail)[-n:])

    # --- Controller protocol ----------------------------------------------------------------
    def reset(self) -> None:
        """(Re)start the sandbox process, load the candidate, and clear host-side state.

        Raises:
            SandboxLoadError: the candidate failed to load (the process is killed).
            SandboxTimeout: loading exceeded ``load_timeout_s``.
        """
        self._kill()
        self._closed = False
        self._started = True
        self.state = {}
        self._spawn()
        try:
            self._send({"type": "load", "source": self.source})
            msg = self._recv(self.load_timeout_s, "load")
        except SandboxTimeout:
            raise
        except SandboxCrashed as exc:
            raise SandboxLoadError(str(exc)) from exc
        if msg.get("type") != "loaded" or msg.get("ok") is not True:
            err = str(msg.get("error") or f"unexpected reply {msg!r}")[:1000]
            self.last_error = err
            self._kill()
            raise SandboxLoadError(err)

    def step(self, obs: dict) -> float:
        """Run one control step. Returns ``u`` (``nan`` if the candidate errored).

        Raises:
            SandboxTimeout: the step exceeded ``step_timeout_s`` (the sandbox is killed).
            SandboxCrashed: the sandbox died or broke protocol.
        """
        if self._proc is None:
            if self._closed:
                raise SandboxCrashed("controller is closed")
            if self._started:
                raise SandboxCrashed(
                    f"sandbox is not running (last failure: {self.last_error}); call reset() to restart"
                )
            self.reset()
        self.step_count += 1
        self._send({"type": "step", "obs": obs, "state": self.state})
        msg = self._recv(self.step_timeout_s, "step")
        if msg.get("type") != "result":
            return self._record_error(f"protocol: unexpected reply type {msg.get('type')!r}: {msg.get('error')}")
        err = msg.get("error")
        if err is not None:
            return self._record_error(str(err)[:1000])
        u = msg.get("u")
        new_state = msg.get("state")
        if isinstance(u, bool) or not isinstance(u, (int, float)) or not math.isfinite(float(u)):
            return self._record_error(f"ValueError: non-finite or non-numeric u {u!r}")
        if not isinstance(new_state, dict):
            return self._record_error("TypeError: reply state is not a dict")
        self.state = new_state
        return float(u)

    def _record_error(self, err: str) -> float:
        self.error_count += 1
        self.last_error = err
        return float("nan")

    def close(self) -> None:
        """Ask the runner to exit, then make sure the process (and container) is gone. Idempotent."""
        if self._closed and self._proc is None:
            return
        self._closed = True
        proc = self._proc
        if proc is not None and proc.poll() is None:
            try:
                if proc.stdin is not None:
                    proc.stdin.write(b'{"type": "close"}\n')
                    proc.stdin.flush()
                    proc.stdin.close()
                proc.wait(timeout=3)
            except (OSError, ValueError, subprocess.TimeoutExpired):
                pass
        self._kill()

    def __del__(self) -> None:
        try:
            self.close()
        except Exception:  # noqa: BLE001, S110 - never raise from a finalizer
            pass


class DockerSandboxController(_RunnerProcessController):
    """Untrusted controller executed inside a disposable, locked-down Docker container.

    One container per :meth:`reset`; it lives for the duration of an episode/suite and is
    removed on :meth:`close` (``--rm`` plus an explicit ``docker kill`` by name).
    """

    isolation = "docker"

    def __init__(
        self,
        source: str,
        name: str,
        step_timeout_s: float = 2.0,
        total_cpu_s: float = 20.0,
        image: str = DEFAULT_IMAGE,
        load_timeout_s: float = 30.0,
    ) -> None:
        super().__init__(source, name, step_timeout_s, total_cpu_s, load_timeout_s)
        self.image = image
        self.container_name: str | None = None

    def _command(self) -> list[str]:
        self.container_name = f"praxion-sbx-{uuid.uuid4().hex[:16]}"
        args = docker_run_args(self.image, container_name=self.container_name)
        # Pass the CPU budget via env (the runner applies RLIMIT_CPU). Insert before the image.
        args[-1:-1] = ["--env", f"PRAXION_SANDBOX_CPU_S={max(1, math.ceil(self.total_cpu_s))}"]
        return args + ["python", "-I", "-S", "-c", RUNNER_SOURCE]

    def _kill_backend(self) -> None:
        if self.container_name is None:
            return
        name, self.container_name = self.container_name, None
        try:
            subprocess.run(["docker", "kill", name], capture_output=True, timeout=15, check=False)
        except (OSError, subprocess.TimeoutExpired):
            pass


class SubprocessDevSandboxController(_RunnerProcessController):
    """**DEV ONLY -- reduced isolation.** Runs the sandbox runner as a plain host subprocess.

    Same protocol and in-process restrictions as the Docker sandbox, but no container: no
    network/filesystem isolation if the in-process layers are bypassed, and on macOS the
    address-space rlimit is not enforced. Must be labelled "reduced isolation, dev only"
    wherever its results are shown.
    """

    isolation = "subprocess_dev_only"

    def _command(self) -> list[str]:
        return [sys.executable, "-I", "-S", "-c", RUNNER_SOURCE]

    def _env(self) -> dict[str, str] | None:
        return {"PRAXION_SANDBOX_CPU_S": str(max(1, math.ceil(self.total_cpu_s)))}


def make_sandbox(source: str, name: str, mode: str, **kwargs: Any) -> Controller:
    """Build a sandboxed controller. ``mode`` is ``"docker"`` or ``"subprocess_dev_only"``."""
    if mode == "docker":
        return DockerSandboxController(source, name, **kwargs)
    if mode == "subprocess_dev_only":
        kwargs.pop("image", None)
        return SubprocessDevSandboxController(source, name, **kwargs)
    raise ValueError(f"unknown sandbox mode {mode!r}; expected 'docker' or 'subprocess_dev_only'")


__all__ = [
    "DEFAULT_IMAGE",
    "DockerSandboxController",
    "SandboxCrashed",
    "SandboxError",
    "SandboxLoadError",
    "SandboxTimeout",
    "SubprocessDevSandboxController",
    "docker_available",
    "docker_run_args",
    "ensure_image",
    "make_sandbox",
]
