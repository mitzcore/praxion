"""Shared controller interface used by baselines, the sandbox, and the trusted runtime.

obs passed to step() is always:
    {"y": float, "target": float, "dt": float, "elapsed_s": float}
step() returns the *requested* actuator command. It may be invalid (NaN, out of range);
the trusted Supervisor decides what is actually applied.
"""
from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class Controller(Protocol):
    name: str
    isolation: str  # "trusted" (baselines) | "docker" | "subprocess_dev_only"

    def reset(self) -> None: ...

    def step(self, obs: dict) -> float: ...

    def close(self) -> None: ...
