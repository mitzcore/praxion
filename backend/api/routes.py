"""REST + SSE routes for the evidence surface."""
from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import Response
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

from backend.api import bundle
from backend.api.manager import FAMILIES, ManagerError, RunManager, StartRequest
from backend.api.stream import replay_events, tail_events


class StrictJSON(Response):
    """JSON with NaN/Inf mapped to null (stored artifacts may contain NaN medians)."""

    media_type = "application/json"

    def render(self, content: Any) -> bytes:
        return bundle.dumps(content).encode("utf-8")


class DisturbanceRequest(BaseModel):
    family: str


_docker_cache: dict[str, Any] = {"at": 0.0, "ok": None}


def _docker_ok() -> bool:
    if time.time() - _docker_cache["at"] > 30 or _docker_cache["ok"] is None:
        from backend.controller.sandbox import docker_available
        _docker_cache["ok"] = docker_available(timeout_s=3.0)
        _docker_cache["at"] = time.time()
    return bool(_docker_cache["ok"])


def build_router(root: Path, manager: RunManager) -> APIRouter:
    r = APIRouter()

    def rdir(run_id: str) -> Path:
        try:
            return bundle.run_dir(root, run_id)
        except bundle.RunNotFound:
            raise HTTPException(404, f"run not found: {run_id}") from None

    def raise_mgr(e: ManagerError) -> None:
        raise HTTPException(e.status, e.reason) from None

    @r.get("/health", response_class=StrictJSON)
    def health() -> Any:
        from backend.agent.prompts import PROMPT_HASH, PROMPT_VERSION
        from backend.config import get_settings
        s = get_settings()
        return {"status": "ok", "sandbox_mode": s.sandbox, "docker_available": _docker_ok(),
                "agent_mode_default": s.agent_mode, "model_default": s.muse_model, "prompt_version": PROMPT_VERSION,
                "prompt_hash": PROMPT_HASH, "artifact_root": str(root), "families": list(FAMILIES),
                "busy_run": (b.run_id if (b := manager.busy_run()) else None)}

    @r.get("/api/runs", response_class=StrictJSON)
    def list_runs() -> Any:
        runs = bundle.list_runs(root)
        for x in runs:
            x["active"] = manager.is_active(x["id"])
        return runs

    @r.post("/api/runs", response_class=StrictJSON)
    def start_run(req: StartRequest) -> Any:
        try:
            run_id = manager.start(req)
        except ManagerError as e:
            raise_mgr(e)
        return {"run_id": run_id}

    @r.get("/api/runs/{run_id}", response_class=StrictJSON)
    def get_run(run_id: str) -> Any:
        out = bundle.get_run(rdir(run_id))
        out["process"] = manager.status(run_id)
        return out

    @r.post("/api/runs/{run_id}/disturbance", response_class=StrictJSON)
    def disturbance(run_id: str, req: DisturbanceRequest) -> Any:
        d = rdir(run_id)
        try:
            manager.disturb(run_id, req.family, bundle.live_summary(d)["stage"])
        except ManagerError as e:
            raise_mgr(e)
        return {"run_id": run_id, "accepted": True}  # family deliberately not echoed

    @r.post("/api/runs/{run_id}/stop", response_class=StrictJSON)
    def stop(run_id: str) -> Any:
        rdir(run_id)
        try:
            return manager.stop(run_id)
        except ManagerError as e:
            raise_mgr(e)

    @r.get("/api/runs/{run_id}/events", response_class=StrictJSON)
    def events(run_id: str, after: int = Query(0, ge=0), limit: int = Query(0, ge=0)) -> Any:
        ev = bundle.read_events(rdir(run_id), after=after)
        return ev[:limit] if limit else ev

    @r.get("/api/runs/{run_id}/stream")
    async def stream(run_id: str, request: Request, replay: int = 0, speed: float = Query(1.0, gt=0),
                     after: int = Query(0, ge=0), max_gap_s: float | None = Query(None, gt=0)) -> EventSourceResponse:
        d = rdir(run_id)
        last_id = request.headers.get("last-event-id")
        if last_id and last_id.isdigit():
            after = max(after, int(last_id))
        if replay:
            gen = replay_events(d, speed=speed, after=after, max_gap_s=max_gap_s)
        else:
            gen = tail_events(d, after=after, is_active=lambda: manager.is_active(run_id))
        return EventSourceResponse(gen, ping=15)

    @r.get("/api/runs/{run_id}/controllers", response_class=StrictJSON)
    def controllers(run_id: str) -> Any:
        return bundle.controllers(rdir(run_id))

    @r.get("/api/runs/{run_id}/evaluations", response_class=StrictJSON)
    def evaluations(run_id: str, traces: str = Query("all", pattern="^(all|disturbance|none)$")) -> Any:
        return bundle.evaluations(rdir(run_id), traces=traces)

    @r.get("/api/runs/{run_id}/experiments", response_class=StrictJSON)
    def experiments(run_id: str) -> Any:
        return bundle.experiments(rdir(run_id))

    @r.get("/api/runs/{run_id}/ledger", response_class=StrictJSON)
    def ledger(run_id: str) -> Any:
        return bundle.ledger(rdir(run_id))

    @r.get("/api/runs/{run_id}/export")
    def export(run_id: str) -> Response:
        d = rdir(run_id)
        return Response(bundle.export_zip(d), media_type="application/zip",
                        headers={"Content-Disposition": f'attachment; filename="{run_id}.zip"'})

    return r
