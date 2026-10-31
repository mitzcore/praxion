"""Run the live loop over several hidden machines (plant seeds) to measure the protocol's distribution.

  uv run python scripts/run_batch.py --model muse-spark-1.3 --seeds 3 7 11 14 18 --disturbance actuator_lag
Each run is a separate process so a failure cannot contaminate the others. Results land under
artifacts/runs/<label>-*; regenerate docs/BENCHMARKS.md afterwards with scripts/run_evaluation.py.
"""
from __future__ import annotations

import argparse
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True)
    ap.add_argument("--seeds", type=int, nargs="+", required=True)
    ap.add_argument("--disturbance", default="actuator_lag")
    ap.add_argument("--label", default=None)
    ap.add_argument("--parallel", type=int, default=1, help="concurrent runs (API + Docker load)")
    ap.add_argument("--reasoning-effort", default=None)
    args = ap.parse_args()
    label = args.label or args.model.replace(".", "").replace("-", "")

    pending = list(args.seeds)
    running: list[tuple[int, subprocess.Popen[bytes], Path]] = []
    results: dict[int, int] = {}
    logs = ROOT / "artifacts" / "batch_logs"
    logs.mkdir(parents=True, exist_ok=True)
    while pending or running:
        while pending and len(running) < args.parallel:
            seed = pending.pop(0)
            log = logs / f"{label}-seed{seed}-{int(time.time())}.log"
            cmd = [sys.executable, str(ROOT / "scripts" / "run_live_demo.py"), "--model", args.model, "--plant-seed",
                   str(seed), "--disturbance", args.disturbance, "--label", f"{label}-s{seed}", "--quiet"]
            if args.reasoning_effort:
                cmd += ["--reasoning-effort", args.reasoning_effort]
            print(f"[start] seed {seed} → {log.name}", flush=True)
            running.append((seed, subprocess.Popen(cmd, stdout=log.open("wb"), stderr=subprocess.STDOUT, cwd=ROOT), log))
        time.sleep(5)
        still = []
        for seed, proc, log in running:
            rc = proc.poll()
            if rc is None:
                still.append((seed, proc, log))
            else:
                results[seed] = rc
                tail = log.read_text().strip().splitlines()[-4:]
                print(f"[done ] seed {seed} rc={rc}\n    " + "\n    ".join(tail), flush=True)
        running = still
    print("\nsummary:", {s: ("ok" if rc == 0 else f"rc={rc}") for s, rc in sorted(results.items())})
    return 0 if all(rc == 0 for rc in results.values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
