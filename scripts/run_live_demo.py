"""Run the full Praxion loop with a real Muse model and record a replayable artifact bundle.

Examples:
  uv run python scripts/run_live_demo.py --model muse-spark-1.3 --plant-seed 7 --disturbance actuator_lag
  uv run python scripts/run_live_demo.py --agent-mode mock --sandbox subprocess_dev_only   # plumbing only
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.agent.mock_agent import MockMuseClient
from backend.agent.muse_client import MuseClient
from backend.agent.orchestrator import Orchestrator, OrchestratorConfig
from backend.agent.session import Budget, Session
from backend.controller.sandbox import docker_available, ensure_image
from backend.plant.tank_sim import TankSimulator
from backend.safety.supervisor import Supervisor
from backend.storage.artifacts import RunStore, new_run_id

FAMILIES = ["actuator_lag", "pump_derate", "extra_leak", "drain_shift"]


def main() -> int:
    load_dotenv()
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default=None, help="muse-wonder-1.0 | muse-spark-1.3 (default: MUSE_MODEL env)")
    ap.add_argument("--agent-mode", choices=["live", "mock"], default="live")
    ap.add_argument("--plant-seed", type=int, default=7, help="hidden machine identity (exploration seeds 1-20)")
    ap.add_argument("--disturbance", choices=FAMILIES + ["none"], default="actuator_lag")
    ap.add_argument("--sandbox", choices=["docker", "subprocess_dev_only"], default="docker")
    ap.add_argument("--max-experiments", type=int, default=12)
    ap.add_argument("--max-candidates", type=int, default=5)
    ap.add_argument("--reasoning-effort", default=None)
    ap.add_argument("--label", default="run")
    ap.add_argument("--root", default="artifacts/runs")
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args()

    if args.sandbox == "docker":
        if not docker_available():
            print("Docker is not available; use --sandbox subprocess_dev_only for development only.", file=sys.stderr)
            return 2
        ensure_image()

    run_id = new_run_id(args.label)
    store = RunStore(run_id, root=Path(args.root))
    plant = TankSimulator()
    session = Session(run_id=run_id, plant_description=plant.public_description(), agent_mode=args.agent_mode,
                      budget=Budget(max_experiments=args.max_experiments, max_candidates=args.max_candidates))
    if args.agent_mode == "mock":
        agent = MockMuseClient()
    else:
        agent = MuseClient(model=args.model, reasoning_effort=args.reasoning_effort, log_path=store.model_calls_path)

    t0 = time.time()

    def on_event(rec: dict) -> None:
        if args.quiet:
            return
        kind = rec["kind"]
        skip = {"samples", "episodes", "hypotheses", "detail", "detector", "ts", "run_id", "seq"}
        payload = {k: v for k, v in rec.items() if k not in skip and k != "kind"}
        print(f"[{time.time() - t0:6.1f}s] {kind:22s} {json.dumps(payload, default=str)[:300]}")

    orch = Orchestrator(session, store, agent, plant, Supervisor(), None,
                        OrchestratorConfig(plant_seed=args.plant_seed, sandbox_mode=args.sandbox), on_event=on_event)
    print(f"run_id={run_id} model={getattr(agent, 'model', '?')} plant_seed={args.plant_seed} "
          f"disturbance={args.disturbance} sandbox={args.sandbox}\n")
    orch.run_discovery()
    if session.stage == "DEPLOYABLE":
        orch.run_monitoring(None if args.disturbance == "none" else args.disturbance)

    totals = getattr(agent, "totals", None)
    print(f"\nfinal stage: {session.stage}")
    print(f"candidates: {[(c.candidate_id, c.status) for c in session.candidates]}")
    if totals:
        print(f"model calls: {totals.calls} (failed {totals.failed_calls}), tokens in/out/reasoning: "
              f"{totals.prompt_tokens}/{totals.completion_tokens}/{totals.reasoning_tokens}, est. cost ${totals.cost_usd:.3f}")
    print(f"artifacts: {store.dir}")
    return 0 if session.stage in {"COMPLETE", "DEPLOYABLE"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
