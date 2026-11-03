"""Praxion evidence surface: FastAPI REST + SSE over the artifact bundle, plus the built UI.

  uv run uvicorn backend.main:app --port 8000
  PRAXION_REPLAY_RUN=<run_id> uv run uvicorn backend.main:app   # UI opens that run in replay
"""
from __future__ import annotations

import os
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from backend.api import bundle
from backend.api.manager import RunManager
from backend.api.routes import StrictJSON, build_router
from backend.storage.artifacts import DEFAULT_ROOT

FRONTEND_DIST = Path(__file__).resolve().parents[1] / "frontend" / "dist"


def create_app(root: Path | None = None, manager: RunManager | None = None, dist: Path | None = FRONTEND_DIST) -> FastAPI:
    root = Path(root or os.getenv("PRAXION_ARTIFACT_ROOT") or DEFAULT_ROOT)
    app = FastAPI(title="Praxion evidence surface", version="0.1.0")
    app.add_middleware(GZipMiddleware, minimum_size=2048)
    app.state.root = root
    app.state.manager = manager or RunManager(root)
    app.include_router(build_router(root, app.state.manager))

    @app.get("/api/config")
    def ui_config() -> JSONResponse:
        """Startup hints for the UI (e.g. replay mode from scripts/replay_run.py)."""
        return JSONResponse({"replay_run": os.getenv("PRAXION_REPLAY_RUN") or None,
                             "replay_speed": float(os.getenv("PRAXION_REPLAY_SPEED", "1") or 1)})

    @app.get("/api/runs/{run_id}/board_verification", response_class=StrictJSON)
    def board_verification(run_id: str) -> object:
        """<run_dir>/board_verification.json verbatim (written by trusted code after a hardware run), or null."""
        try:
            d = bundle.run_dir(root, run_id)
        except bundle.RunNotFound:
            raise HTTPException(404, f"run not found: {run_id}") from None
        data = bundle._read_json(d / "board_verification.json")
        return data if isinstance(data, dict) else None

    if dist is not None and (dist / "index.html").exists():
        if (dist / "assets").is_dir():
            app.mount("/assets", StaticFiles(directory=dist / "assets"), name="assets")

        @app.get("/", include_in_schema=False)
        def index() -> FileResponse:
            return FileResponse(dist / "index.html")

        @app.get("/{name}", include_in_schema=False)
        def static_file(name: str) -> FileResponse:
            p = (dist / name).resolve()
            if p.parent == dist.resolve() and p.is_file():
                return FileResponse(p)
            return FileResponse(dist / "index.html")

    return app


app = create_app()
