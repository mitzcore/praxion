"""Regenerate docs/BENCHMARKS.md (and artifacts/benchmarks/latest.json) from stored runs plus fresh,
deterministic scoring on the frozen scenarios. One command reproduces every number we claim.

Examples:
  uv run python scripts/run_evaluation.py                                  # docker sandbox, live runs only
  uv run python scripts/run_evaluation.py --sandbox subprocess_dev_only    # dev only, labeled in the doc
  uv run python scripts/run_evaluation.py --include-mock --run <run_id>    # plumbing check, rows labeled MOCK
"""
from __future__ import annotations

import argparse
import shlex
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.evaluation.benchmarks import ALL_BASELINES, BenchmarkError, build_benchmarks, write_outputs


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--sandbox", choices=["docker", "subprocess_dev_only"], default="docker")
    ap.add_argument("--root", default="artifacts", help="artifact root (runs live under <root>/runs)")
    ap.add_argument("--run", action="append", dest="runs", help="only these run ids (repeatable)")
    ap.add_argument("--include-mock", action="store_true", help="include mock runs (every row labeled MOCK)")
    ap.add_argument("--plant-seed", type=int, default=None,
                    help="fallback plant seed for runs whose stored evaluation lacks audit entries")
    ap.add_argument("--baseline", action="append", choices=sorted(ALL_BASELINES), dest="baselines",
                    help="restrict baselines (default: all)")
    ap.add_argument("--out", default="docs/BENCHMARKS.md")
    ap.add_argument("--json-out", default=None, help="default: <root>/benchmarks/latest.json")
    ap.add_argument("--cache-dir", default=None, help="default: <root>/benchmarks/cache")
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args(argv)

    root = Path(args.root)
    command = "uv run python scripts/run_evaluation.py " + " ".join(shlex.quote(a) for a in (argv or sys.argv[1:]))
    try:
        data = build_benchmarks(
            root, sandbox_mode=args.sandbox, cache_dir=Path(args.cache_dir or root / "benchmarks" / "cache"),
            include_mock=args.include_mock, plant_seed_override=args.plant_seed, run_ids=args.runs,
            baselines=tuple(args.baselines or ALL_BASELINES), progress=None if args.quiet else print,
        )
    except BenchmarkError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    json_out = Path(args.json_out or root / "benchmarks" / "latest.json")
    write_outputs(data, markdown_path=Path(args.out), json_path=json_out, command=command.strip())
    print(f"wrote {args.out} and {json_out}: {len(data['runs'])} run(s), {len(data['skipped'])} skipped, "
          f"cache {data['cache']['hits']} hits / {data['cache']['misses']} misses")
    for s in data["skipped"]:
        print(f"  skipped {s['run_id']}: {s['reason']}")
    return 1 if any(r.get("aborted") for r in data["runs"]) else 0


if __name__ == "__main__":
    raise SystemExit(main())
