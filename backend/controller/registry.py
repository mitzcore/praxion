"""Byte-exact, hashed registry of model-authored controller candidates.

Layout under ``root`` (normally ``artifacts/``)::

    runs/<run_id>/controller_vN.py            # EXACT bytes of the model's source (UTF-8)
    runs/<run_id>/controller_vN.meta.json     # Candidate metadata + rationale + extra
    runs/<run_id>/controller_diff_vA_vB.patch # unified diff written by Registry.diff

The registry never reformats, strips, or newline-normalises a source: files are written in
binary mode and refused if they already exist, so a version can never be silently replaced.
"""
from __future__ import annotations

import difflib
import hashlib
import json
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel

_RUN_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")
_CANDIDATE_ID_RE = re.compile(r"^(?P<run>.+)-v(?P<ver>[1-9][0-9]*)$")
_SOURCE_RE = re.compile(r"^controller_v(?P<ver>[1-9][0-9]*)\.py$")


class Candidate(BaseModel):
    """Metadata for one registered controller source."""

    id: str
    run_id: str
    version: int
    path: Path
    sha256: str
    parent_id: str | None
    model_id: str
    prompt_hash: str
    created_at: str
    byte_length: int
    rationale: str = ""
    extra: dict[str, Any] = {}


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class Registry:
    """Persist and retrieve controller candidates under ``root/runs/<run_id>/``."""

    def __init__(self, root: Path | str) -> None:
        self.root = Path(root)

    # --- paths ------------------------------------------------------------------------------
    def run_dir(self, run_id: str) -> Path:
        """Directory for ``run_id`` (validated against path traversal)."""
        if not _RUN_ID_RE.match(run_id):
            raise ValueError(f"invalid run_id {run_id!r}")
        return self.root / "runs" / run_id

    @staticmethod
    def parse_id(candidate_id: str) -> tuple[str, int]:
        """Split ``"<run_id>-v<N>"`` into ``(run_id, N)``."""
        m = _CANDIDATE_ID_RE.match(candidate_id)
        if not m:
            raise ValueError(f"invalid candidate id {candidate_id!r}")
        return m.group("run"), int(m.group("ver"))

    def _paths(self, run_id: str, version: int) -> tuple[Path, Path]:
        d = self.run_dir(run_id)
        return d / f"controller_v{version}.py", d / f"controller_v{version}.meta.json"

    # --- write ------------------------------------------------------------------------------
    def persist(
        self,
        source: str,
        *,
        run_id: str,
        parent_id: str | None,
        model_id: str,
        prompt_hash: str,
        rationale: str,
        extra: dict | None = None,
    ) -> Candidate:
        """Store ``source`` byte-for-byte as the next version for ``run_id``."""
        data = source.encode("utf-8")
        d = self.run_dir(run_id)
        d.mkdir(parents=True, exist_ok=True)
        existing = [int(m.group("ver")) for p in d.iterdir() if (m := _SOURCE_RE.match(p.name))]
        version = max(existing, default=0) + 1
        src_path, meta_path = self._paths(run_id, version)
        with open(src_path, "xb") as fh:  # binary, exclusive: no newline translation, no overwrite
            fh.write(data)
        cand = Candidate(
            id=f"{run_id}-v{version}",
            run_id=run_id,
            version=version,
            path=src_path,
            sha256=_sha256(data),
            parent_id=parent_id,
            model_id=model_id,
            prompt_hash=prompt_hash,
            created_at=datetime.now(UTC).isoformat(),
            byte_length=len(data),
            rationale=rationale,
            extra=dict(extra or {}),
        )
        with open(meta_path, "x", encoding="utf-8") as fh:
            fh.write(cand.model_dump_json(indent=2))
        return cand

    # --- read -------------------------------------------------------------------------------
    def get(self, candidate_id: str) -> Candidate:
        """Load a candidate's metadata by id."""
        run_id, version = self.parse_id(candidate_id)
        _, meta_path = self._paths(run_id, version)
        return Candidate.model_validate_json(meta_path.read_text(encoding="utf-8"))

    def load_source(self, candidate_id: str) -> str:
        """Return the stored source exactly as persisted."""
        run_id, version = self.parse_id(candidate_id)
        src_path, _ = self._paths(run_id, version)
        return src_path.read_bytes().decode("utf-8")

    def verify(self, candidate: Candidate) -> bool:
        """Re-hash the stored file and compare against the recorded sha256 and length."""
        try:
            data = Path(candidate.path).read_bytes()
        except OSError:
            return False
        return _sha256(data) == candidate.sha256 and len(data) == candidate.byte_length

    def list(self, run_id: str) -> list[Candidate]:
        """All candidates for ``run_id``, ordered by version."""
        d = self.run_dir(run_id)
        if not d.is_dir():
            return []
        versions = sorted(int(m.group("ver")) for p in d.iterdir() if (m := _SOURCE_RE.match(p.name)))
        return [self.get(f"{run_id}-v{v}") for v in versions]

    # --- diff -------------------------------------------------------------------------------
    def diff(self, old_id: str, new_id: str) -> str:
        """Unified diff of two stored sources; also written to the new candidate's run dir."""
        old_run, old_v = self.parse_id(old_id)
        new_run, new_v = self.parse_id(new_id)
        old_src = self.load_source(old_id)
        new_src = self.load_source(new_id)
        out: list[str] = []
        for line in difflib.unified_diff(
            old_src.splitlines(keepends=True),
            new_src.splitlines(keepends=True),
            fromfile=f"a/{old_run}/controller_v{old_v}.py",
            tofile=f"b/{new_run}/controller_v{new_v}.py",
        ):
            if line.endswith(("\n", "\r")):
                out.append(line)
            else:
                out.append(line + "\n\\ No newline at end of file\n")
        text = "".join(out)
        patch_path = self.run_dir(new_run) / f"controller_diff_v{old_v}_v{new_v}.patch"
        patch_path.write_bytes(text.encode("utf-8"))
        return text

    def to_json(self, candidate: Candidate) -> str:
        """JSON form of a candidate (for event logs)."""
        return json.dumps(json.loads(candidate.model_dump_json()), sort_keys=True)
