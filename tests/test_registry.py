"""Registry: byte-exact persistence, hashing, versioning, diffs."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from backend.controller.registry import Candidate, Registry

TRICKY = [
    "def control(obs, state):\r\n    return 0.5, state\r\n",  # CRLF
    "def control(obs, state):   \n    return 0.5, state  \t\n\n\n",  # trailing whitespace, blank lines
    "def control(obs, state):\n\treturn 0.5, state\n",  # tabs
    "# régulateur — 水位 ✓\ndef control(obs, state):\n    return 0.5, {'note': 'ü'}\n",  # unicode
    "def control(obs, state):\n    return 0.5, state",  # no trailing newline
    "\ufeffdef control(obs, state):\r\n    return 0.5, state\r",  # BOM, CRLF, lone CR at end
]


def _persist(reg: Registry, source: str, run_id: str = "run1", parent: str | None = None) -> Candidate:
    return reg.persist(source, run_id=run_id, parent_id=parent, model_id="muse-wonder-1.0",
                       prompt_hash="abc123", rationale="because", extra={"stage": "AUTHORING"})


@pytest.mark.parametrize("source", TRICKY)
def test_exact_bytes(tmp_path: Path, source: str) -> None:
    reg = Registry(tmp_path)
    c = _persist(reg, source)
    assert Path(c.path).read_bytes() == source.encode()
    assert reg.load_source(c.id) == source
    assert c.sha256 == hashlib.sha256(source.encode()).hexdigest()
    assert c.byte_length == len(source.encode())
    assert reg.verify(c)


def test_layout_and_metadata(tmp_path: Path) -> None:
    reg = Registry(tmp_path)
    c = _persist(reg, TRICKY[0])
    assert c.path == tmp_path / "runs" / "run1" / "controller_v1.py"
    meta = json.loads((tmp_path / "runs" / "run1" / "controller_v1.meta.json").read_text())
    assert meta["sha256"] == c.sha256
    assert meta["model_id"] == "muse-wonder-1.0"
    assert meta["prompt_hash"] == "abc123"
    assert meta["rationale"] == "because"
    assert meta["extra"] == {"stage": "AUTHORING"}
    assert meta["created_at"].endswith("+00:00")
    assert reg.get(c.id) == c


def test_versions_increment_per_run(tmp_path: Path) -> None:
    reg = Registry(tmp_path)
    a1 = _persist(reg, "a")
    a2 = _persist(reg, "b", parent=a1.id)
    b1 = _persist(reg, "c", run_id="run2")
    assert (a1.id, a1.version) == ("run1-v1", 1)
    assert (a2.id, a2.version, a2.parent_id) == ("run1-v2", 2, "run1-v1")
    assert (b1.id, b1.version) == ("run2-v1", 1)
    assert [c.id for c in reg.list("run1")] == ["run1-v1", "run1-v2"]
    assert reg.list("missing") == []
    # A fresh Registry over the same root continues numbering.
    assert _persist(Registry(tmp_path), "d").version == 3


def test_verify_detects_tampering(tmp_path: Path) -> None:
    reg = Registry(tmp_path)
    c = _persist(reg, TRICKY[1])
    Path(c.path).write_bytes(TRICKY[1].replace("   \n", "\n").encode())
    assert not reg.verify(c)
    Path(c.path).unlink()
    assert not reg.verify(c)


def test_diff_written(tmp_path: Path) -> None:
    reg = Registry(tmp_path)
    v1 = _persist(reg, "def control(obs, state):\n    return 0.5, state\n")
    v2 = _persist(reg, "def control(obs, state):\n    return 0.6, state", parent=v1.id)
    d = reg.diff(v1.id, v2.id)
    assert "-    return 0.5, state\n" in d
    assert "+    return 0.6, state\n\\ No newline at end of file\n" in d
    patch = tmp_path / "runs" / "run1" / "controller_diff_v1_v2.patch"
    assert patch.read_bytes() == d.encode()


@pytest.mark.parametrize("bad", ["../escape", "/abs", "", ".hidden", "a/b"])
def test_rejects_unsafe_run_ids(tmp_path: Path, bad: str) -> None:
    with pytest.raises(ValueError):
        _persist(Registry(tmp_path), "x", run_id=bad)


def test_no_overwrite(tmp_path: Path) -> None:
    reg = Registry(tmp_path)
    c = _persist(reg, "first")
    # Simulate a racing writer that already took v2's slot.
    (c.path.parent / "controller_v2.py").write_bytes(b"other")
    c3 = _persist(reg, "second")
    assert c3.version == 3
    assert Path(c.path).read_bytes() == b"first"
