"""RunManager: owns at most one orchestrator thread at a time.

The orchestrator writes the event log and artifacts itself; the API only reads files. The
manager keeps finished in-process orchestrators so a DEPLOYABLE run can be monitored later.
A run recorded by another process (or before a restart) cannot be resumed: the trusted
session state needed for monitoring lives only in memory.
"""
from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field

log = logging.getLogger("praxion.api")

FAMILIES = ("actuator_lag", "pump_derate", "extra_leak", "drain_shift")


class StartRequest(BaseModel):
    label: str = Field("run", pattern=r"^[A-Za-z0-9_]{1,40}$")
    model: str | None = None
    agent_mode: Literal["live", "mock"] = "live"
    plant_seed: int = Field(7, ge=0, le=10_000)
    sandbox_mode: Literal["docker", "subprocess_dev_only"] = "docker"
    max_experiments: int = Field(12, ge=1, le=40)
    max_candidates: int = Field(5, ge=1, le=10)


class ManagerError(Exception):
    def __init__(self, status: int, reason: str) -> None:
        super().__init__(reason)
        self.status = status
        self.reason = reason


@dataclass
class ActiveRun:
    run_id: str
    session: Any
    orchestrator: Any
    thread: threading.Thread | None = None
    phase: str = "discovery"
    error: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)

    def busy(self) -> bool:
        return self.thread is not None and self.thread.is_alive()


Builder = Callable[[StartRequest, Path], tuple[str, Any, Any]]


def default_builder(req: StartRequest, root: Path) -> tuple[str, Any, Any]:
    """Construct exactly as scripts/run_live_demo.py does. Returns (run_id, session, orchestrator)."""
    from backend.agent.mock_agent import MockMuseClient
    from backend.agent.muse_client import MuseClient, MuseError
    from backend.agent.orchestrator import Orchestrator, OrchestratorConfig
    from backend.agent.session import Budget, Session
    from backend.controller.sandbox import docker_available, ensure_image
    from backend.plant.tank_sim import TankSimulator
    from backend.safety.supervisor import Supervisor
    from backend.storage.artifacts import RunStore, new_run_id

    if req.sandbox_mode == "docker":
        if not docker_available():
            raise ManagerError(400, "Docker is not available; subprocess_dev_only is for development only")
        ensure_image()
    run_id = new_run_id(req.label)
    plant = TankSimulator()
    if req.agent_mode == "mock":
        agent: Any = MockMuseClient()
    else:
        try:
            agent = MuseClient(model=req.model, log_path=root / run_id / "model_calls.jsonl")
        except MuseError as e:
            raise ManagerError(400, f"live agent unavailable: {e}") from e
    store = RunStore(run_id, root=root)
    session = Session(run_id=run_id, plant_description=plant.public_description(), agent_mode=req.agent_mode,
                      budget=Budget(max_experiments=req.max_experiments, max_candidates=req.max_candidates))
    orch = Orchestrator(session, store, agent, plant, Supervisor(), None,
                        OrchestratorConfig(plant_seed=req.plant_seed, sandbox_mode=req.sandbox_mode))
    return run_id, session, orch


class RunManager:
    def __init__(self, root: Path, builder: Builder | None = None) -> None:
        self.root = root
        self.builder = builder or default_builder
        self._lock = threading.Lock()
        self._runs: dict[str, ActiveRun] = {}

    # ------------------------------------------------------------- queries
    def busy_run(self) -> ActiveRun | None:
        return next((r for r in self._runs.values() if r.busy()), None)

    def get(self, run_id: str) -> ActiveRun | None:
        return self._runs.get(run_id)

    def is_active(self, run_id: str) -> bool:
        r = self._runs.get(run_id)
        return bool(r and r.busy())

    def status(self, run_id: str) -> dict[str, Any] | None:
        r = self._runs.get(run_id)
        if r is None:
            return None
        return {"in_process": True, "busy": r.busy(), "phase": r.phase, "stage": r.session.stage,
                "stop_requested": bool(r.session.stop_requested), "error": r.error}

    # ------------------------------------------------------------- actions
    def start(self, req: StartRequest) -> str:
        with self._lock:
            b = self.busy_run()
            if b is not None:
                raise ManagerError(409, f"run {b.run_id} is still running ({b.phase}); one run at a time")
            run_id, session, orch = self.builder(req, self.root)
            ar = ActiveRun(run_id=run_id, session=session, orchestrator=orch, phase="discovery")
            ar.thread = threading.Thread(target=self._guard, args=(ar, orch.run_discovery), name=f"discovery-{run_id}",
                                         daemon=True)
            self._runs[run_id] = ar
            ar.thread.start()
            return run_id

    def disturb(self, run_id: str, family: str, disk_stage: str | None) -> None:
        if family not in FAMILIES:
            raise ManagerError(422, f"unknown disturbance family; expected one of {', '.join(FAMILIES)}")
        with self._lock:
            b = self.busy_run()
            if b is not None:
                raise ManagerError(409, f"run {b.run_id} is still running ({b.phase})")
            ar = self._runs.get(run_id)
            if ar is None:
                stage = disk_stage or "unknown"
                raise ManagerError(409, f"run is {stage} on disk and not loaded in this server process; monitoring "
                                        "needs the live trusted session, so only runs started here can be disturbed")
            if ar.session.stage != "DEPLOYABLE":
                raise ManagerError(409, f"run stage is {ar.session.stage}; a disturbance needs DEPLOYABLE")
            ar.phase = "monitoring"
            # The family is passed to the orchestrator only; it is never logged or returned here.
            ar.thread = threading.Thread(target=self._guard, args=(ar, lambda: ar.orchestrator.run_monitoring(family)),
                                         name=f"monitoring-{run_id}", daemon=True)
            ar.thread.start()

    def stop(self, run_id: str) -> dict[str, Any]:
        ar = self._runs.get(run_id)
        if ar is None:
            raise ManagerError(409, "run is not loaded in this server process")
        if not ar.busy():
            raise ManagerError(409, f"run is not running (stage {ar.session.stage})")
        ar.session.stop_requested = True
        return {"run_id": run_id, "stop_requested": True,
                "note": "takes effect at the next budget check (between model calls/experiments)"}

    @staticmethod
    def _guard(ar: ActiveRun, fn: Callable[[], Any]) -> None:
        try:
            fn()
        except Exception as e:
            ar.error = f"{type(e).__name__}: {e}"
            log.exception("run %s crashed", ar.run_id)
