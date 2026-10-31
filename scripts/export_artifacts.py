"""Zip one run bundle with the benchmark report and a fresh audit, for judges.

  uv run python scripts/export_artifacts.py <run_id> [--out path.zip] [--root artifacts/runs]

Archive layout:
  runs/<run_id>/...              the run directory, byte-for-byte
  docs/BENCHMARKS.md             if present
  benchmarks/latest.json         raw benchmark numbers, if present
  AUDIT.txt                      output of scripts/audit_run.py for this run (run now)
  MANIFEST.json                  sha256 of every file in the archive (except itself)
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import sys
import time
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def _load_audit():
    spec = importlib.util.spec_from_file_location("praxion_audit_run", ROOT / "scripts" / "audit_run.py")
    mod = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
    sys.modules[spec.name] = mod  # dataclasses resolve annotations through sys.modules
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


def export(run_id: str, *, runs_root: Path, out: Path, benchmarks_md: Path, benchmarks_json: Path) -> tuple[Path, bool]:
    run_dir = runs_root / run_id
    if not run_dir.is_dir():
        raise FileNotFoundError(run_dir)
    audit_mod = _load_audit()
    checks = audit_mod.audit(run_dir)
    rp = run_dir / "result.json"
    result = json.loads(rp.read_text()) if rp.exists() else None
    audit_text = audit_mod.format_checks(run_id, checks, result) + "\n"
    audit_ok = all(c.status != "FAIL" for c in checks)

    manifest: dict[str, str] = {}
    out.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(out, "w", compression=zipfile.ZIP_DEFLATED) as z:
        def add_bytes(arc: str, data: bytes) -> None:
            z.writestr(arc, data)
            manifest[arc] = hashlib.sha256(data).hexdigest()

        for p in sorted(run_dir.rglob("*")):
            if p.is_file():
                add_bytes(f"runs/{run_id}/{p.relative_to(run_dir).as_posix()}", p.read_bytes())
        if benchmarks_md.exists():
            add_bytes("docs/BENCHMARKS.md", benchmarks_md.read_bytes())
        if benchmarks_json.exists():
            add_bytes("benchmarks/latest.json", benchmarks_json.read_bytes())
        add_bytes("AUDIT.txt", audit_text.encode())
        z.writestr("MANIFEST.json", json.dumps({"run_id": run_id, "exported_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
                                                "audit_passed": audit_ok, "files": manifest}, indent=1))
    return out, audit_ok


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Export a run bundle + BENCHMARKS.md + audit as a zip.")
    ap.add_argument("run_id")
    ap.add_argument("--out", default=None, help="default: artifacts/exports/<run_id>.zip")
    ap.add_argument("--root", default="artifacts/runs")
    ap.add_argument("--benchmarks", default="docs/BENCHMARKS.md")
    ap.add_argument("--benchmarks-json", default="artifacts/benchmarks/latest.json")
    args = ap.parse_args(argv)
    out = Path(args.out or f"artifacts/exports/{args.run_id}.zip")
    try:
        path, ok = export(args.run_id, runs_root=Path(args.root), out=out, benchmarks_md=Path(args.benchmarks),
                          benchmarks_json=Path(args.benchmarks_json))
    except FileNotFoundError as e:
        print(f"error: run directory not found: {e}", file=sys.stderr)
        return 2
    print(f"wrote {path} (audit {'PASS' if ok else 'FAIL'}; see AUDIT.txt inside)")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
