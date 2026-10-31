"""Serve the evidence surface in replay mode for one recorded run.

  uv run python scripts/replay_run.py <run_id> [--speed 4] [--port 8000] [--root artifacts/runs]

The UI opens that run and re-emits its stored event log paced by the recorded timestamps,
labeled REPLAY with the run id and original start time. Nothing is recomputed.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("run_id")
    ap.add_argument("--speed", type=float, default=1.0)
    ap.add_argument("--port", type=int, default=8000)
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--root", default=os.getenv("PRAXION_ARTIFACT_ROOT", "artifacts/runs"))
    args = ap.parse_args()

    d = Path(args.root) / args.run_id
    log = d / "event_log.jsonl"
    if not log.exists():
        print(f"no event log at {log}", file=sys.stderr)
        return 2
    lines = [json.loads(x) for x in log.read_text().splitlines() if x.strip()]
    started = datetime.fromtimestamp(lines[0]["ts"], tz=UTC).isoformat() if lines else "?"
    duration = lines[-1]["ts"] - lines[0]["ts"] if lines else 0.0

    os.environ["PRAXION_ARTIFACT_ROOT"] = str(Path(args.root))
    os.environ["PRAXION_REPLAY_RUN"] = args.run_id
    os.environ["PRAXION_REPLAY_SPEED"] = str(args.speed)
    url = f"http://{args.host}:{args.port}/?run={args.run_id}&replay=1&speed={args.speed:g}"
    print(f"REPLAY of {args.run_id} (recorded {started}, {len(lines)} events, {duration:.0f} s at 1x)")
    print(f"open {url}", flush=True)

    import uvicorn
    uvicorn.run("backend.main:app", host=args.host, port=args.port, log_level="warning")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
