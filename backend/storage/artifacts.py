"""Per-run artifact bundle on disk. JSONL event log is the source of truth; everything the UI
or the benchmark report shows must be reconstructible from this directory alone."""
from __future__ import annotations

import json
import os
import time
import uuid
from pathlib import Path
from typing import Any

DEFAULT_ROOT = Path(os.getenv("PRAXION_ARTIFACT_ROOT", "artifacts/runs"))


def new_run_id(prefix: str = "run") -> str:
    return f"{prefix}-{time.strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:6]}"


class RunStore:
    """Append-only event log plus named JSON/text artifacts for one run."""

    def __init__(self, run_id: str, root: Path | None = None) -> None:
        self.run_id = run_id
        self.dir = (root or DEFAULT_ROOT) / run_id
        self.dir.mkdir(parents=True, exist_ok=True)
        (self.dir / "agent_view_snapshots").mkdir(exist_ok=True)
        self._event_path = self.dir / "event_log.jsonl"
        self._seq = self._count_events()

    # ---------------------------------------------------------------- events
    def event(self, kind: str, **payload: Any) -> dict[str, Any]:
        """Append one event. ``kind`` examples: stage, experiment_proposed, experiment_result,
        candidate_registered, static_check, sandbox_check, evaluation, model_call, degradation,
        disturbance_triggered, stop, error."""
        self._seq += 1
        rec = {"seq": self._seq, "ts": time.time(), "run_id": self.run_id, "kind": kind, **payload}
        with self._event_path.open("a") as f:
            f.write(json.dumps(rec, default=_json_default) + "\n")
        return rec

    def events(self, kind: str | None = None) -> list[dict[str, Any]]:
        if not self._event_path.exists():
            return []
        out = []
        with self._event_path.open() as f:
            for line in f:
                if line.strip():
                    rec = json.loads(line)
                    if kind is None or rec.get("kind") == kind:
                        out.append(rec)
        return out

    def _count_events(self) -> int:
        if not self._event_path.exists():
            return 0
        with self._event_path.open() as f:
            return sum(1 for line in f if line.strip())

    # ------------------------------------------------------------- artifacts
    def write_json(self, name: str, data: Any) -> Path:
        p = self.dir / name
        p.write_text(json.dumps(data, indent=1, default=_json_default))
        return p

    def read_json(self, name: str) -> Any:
        return json.loads((self.dir / name).read_text())

    def write_text(self, name: str, text: str) -> Path:
        p = self.dir / name
        p.write_text(text)
        return p

    def snapshot_view(self, stage: str, index: int, view: dict[str, Any]) -> Path:
        """Every agent view sent to the model is kept, so the blindness test can audit real runs."""
        p = self.dir / "agent_view_snapshots" / f"{index:03d}_{stage}.json"
        p.write_text(json.dumps(view, indent=1, default=_json_default))
        return p

    def view_snapshots(self) -> list[dict[str, Any]]:
        d = self.dir / "agent_view_snapshots"
        return [json.loads(p.read_text()) for p in sorted(d.glob("*.json"))]

    @property
    def model_calls_path(self) -> Path:
        return self.dir / "model_calls.jsonl"


def _json_default(o: Any) -> Any:
    if hasattr(o, "model_dump"):
        return o.model_dump()
    if hasattr(o, "tolist"):
        return o.tolist()
    if isinstance(o, Path):
        return str(o)
    return str(o)
