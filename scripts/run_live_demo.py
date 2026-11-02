"""Run the full Praxion loop with a real Muse model and record a replayable artifact bundle.

Examples:
  uv run python scripts/run_live_demo.py --model muse-spark-1.3 --plant-seed 7 --disturbance actuator_lag
  uv run python scripts/run_live_demo.py --agent-mode mock --sandbox subprocess_dev_only   # plumbing only
  uv run python scripts/run_live_demo.py --plant tclab_sim --disturbance actuator_lag      # TCLab simulator
  uv run python scripts/run_live_demo.py --plant tclab --port /dev/cu.usbmodem1101         # physical heater; scored on a fitted twin
"""
from __future__ import annotations

import argparse
import contextlib
import json
import signal
import sys
import time
from pathlib import Path

from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.agent.mock_agent import MockMuseClient
from backend.agent.muse_client import MuseClient
from backend.agent.orchestrator import Orchestrator, OrchestratorConfig
from backend.agent.session import Budget, Objective, PublicConstraints, Session
from backend.controller.sandbox import docker_available, ensure_image
from backend.plant.base import PlantAdapter
from backend.plant.tank_sim import TankSimulator
from backend.profiles import PlantProfile, get_profile
from backend.safety.supervisor import SafetyLimits, Supervisor
from backend.storage.artifacts import RunStore, new_run_id

FAMILIES = ["actuator_lag", "pump_derate", "extra_leak", "drain_shift"]
PLANTS = ["tank", "tclab_sim", "tclab"]


class PlantUnavailable(RuntimeError):
    pass


def _import_tclab(name: str):
    try:
        from backend.plant import tclab_plant
    except ImportError as e:
        raise PlantUnavailable(f"backend.plant.tclab_plant is not available ({e}); it is needed for --plant {name}") from e
    attr = "TCLabSim" if name == "tclab_sim" else "TCLabHardware"
    cls = getattr(tclab_plant, attr, None)
    if cls is None:
        raise PlantUnavailable(f"backend.plant.tclab_plant has no {attr}; it is needed for --plant {name}")
    return cls


def build_plant(name: str, port: str | None) -> PlantAdapter:
    """Small plant factory. TCLab classes are imported lazily so the tank path never needs them."""
    if name == "tank":
        return TankSimulator()
    cls = _import_tclab(name)
    if name == "tclab_sim":
        return cls()
    if not port:
        raise PlantUnavailable("--plant tclab needs --port (e.g. /dev/cu.usbmodem1101 or COM3)")
    return cls(port=port)


def build_eval_plant_factory(name: str, eval_plant: str, plant: PlantAdapter):
    """Evaluator plant. tank + same → None (the evaluator's default TankSimulator: bit-identical to every
    recorded benchmark). tclab_sim + same → a fresh TCLabSim per episode. twin → "twin" (the orchestrator
    fits a ThermalTwin from the discovery experiments). tclab + same → the physical board itself (slow)."""
    if eval_plant == "twin":
        try:
            from backend.plant import thermal_twin  # noqa: F401 - availability check only
        except ImportError as e:
            raise PlantUnavailable(f"backend.plant.thermal_twin is not available ({e}); needed for --eval-plant twin") from e
        return "twin"
    if name == "tank":
        return None
    if name == "tclab_sim":
        return _import_tclab(name)
    print("WARNING: --plant tclab --eval-plant same scores every hidden scenario on the physical board "
          "(~10 x 900 s held-out + disturbance suites, hours of wall time).", file=sys.stderr)
    return lambda: plant


def session_settings(profile: PlantProfile, max_experiments: int | None) -> dict:
    """Objective, public constraints and budget for the agent, all from the profile.

    The tank keeps the Session defaults byte-for-byte (its agent-facing PublicConstraints tell the model
    worst_case_rate_per_unit_u=0.08 while the trusted envelope uses 0.10; changing what the agent is told
    would change the recorded tank protocol)."""
    if profile.name == "tank":
        return {"objective": Objective(), "constraints": PublicConstraints(),
                "budget_kw": {"max_experiments": max_experiments if max_experiments is not None else profile.max_experiments}}
    return {
        "objective": Objective(target=profile.target, band=profile.band, settle_s=profile.settle_s),
        "constraints": PublicConstraints(
            u_range=(0.0, 1.0), soft_high_limit=profile.soft_high_limit, hard_cutoff=profile.hard_cutoff,
            max_single_experiment_s=profile.max_single_experiment_s,
            after_change_max_single_experiment_s=profile.after_change_max_single_experiment_s,
            worst_case_rate_per_unit_u=profile.worst_case_rate_per_unit_u,
        ),
        "budget_kw": {
            "max_experiments": max_experiments if max_experiments is not None else profile.max_experiments,
            "min_experiments_before_generate": profile.min_experiments_before_generate,
        },
    }


def main() -> int:
    load_dotenv()
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default=None, help="muse-wonder-1.0 | muse-spark-1.3 (default: MUSE_MODEL env)")
    ap.add_argument("--agent-mode", choices=["live", "mock"], default="live")
    ap.add_argument("--plant-seed", type=int, default=7, help="hidden machine identity (exploration seeds 1-20)")
    ap.add_argument("--disturbance", choices=FAMILIES + ["none"], default="actuator_lag")
    ap.add_argument("--sandbox", choices=["docker", "subprocess_dev_only"], default="docker")
    ap.add_argument("--plant", choices=PLANTS, default="tank", help="plant profile (default: tank, the benchmark plant)")
    ap.add_argument("--port", default=None, help="serial port of the physical TCLab board (--plant tclab)")
    ap.add_argument("--eval-plant", choices=["same", "twin"], default=None,
                    help="evaluator plant: same simulator class, or a ThermalTwin fitted from discovery "
                         "(default: twin for --plant tclab, same otherwise)")
    ap.add_argument("--max-experiments", type=int, default=None, help="default: the profile's max_experiments")
    ap.add_argument("--max-candidates", type=int, default=5)
    ap.add_argument("--max-wall-clock-s", type=float, default=None,
                    help="default: 30 min for simulators, 3 h for --plant tclab (a hardware run takes 60-75 min)")
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

    profile = get_profile(args.plant)
    eval_plant = args.eval_plant or ("twin" if args.plant == "tclab" else "same")
    try:
        plant = build_plant(args.plant, args.port)
        eval_factory = build_eval_plant_factory(args.plant, eval_plant, plant)
    except PlantUnavailable as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    limits = SafetyLimits.from_profile(profile)
    operator_disturbance = args.plant == "tclab" and args.disturbance != "none"

    run_id = new_run_id(args.label)
    store = RunStore(run_id, root=Path(args.root))
    ss = session_settings(profile, args.max_experiments)
    budget_kw = dict(ss["budget_kw"])
    if args.max_wall_clock_s is not None:
        budget_kw["max_wall_clock_s"] = float(args.max_wall_clock_s)
    elif args.plant == "tclab":
        budget_kw["max_wall_clock_s"] = 3 * 3600.0  # real time: the 30 min simulator default stops a hardware run mid-repair
    session = Session(run_id=run_id, plant_description=plant.public_description(), agent_mode=args.agent_mode,
                      objective=ss["objective"], constraints=ss["constraints"],
                      budget=Budget(max_candidates=args.max_candidates, **budget_kw))
    if args.agent_mode == "mock":
        agent = MockMuseClient()
    else:
        agent = MuseClient(model=args.model, reasoning_effort=args.reasoning_effort, log_path=store.model_calls_path)

    t0 = time.time()

    show_c = profile.y_unit == "°C"

    def on_event(rec: dict) -> None:
        if args.quiet:
            return
        kind = rec["kind"]
        skip = {"samples", "episodes", "hypotheses", "detail", "detector", "ts", "run_id", "seq"}
        payload = {k: v for k, v in rec.items() if k not in skip and k != "kind"}
        if show_c:
            payload = _with_celsius(payload, profile)
        print(f"[{time.time() - t0:6.1f}s] {kind:22s} {json.dumps(payload, default=str, ensure_ascii=False)[:300]}")

    cfg = OrchestratorConfig(plant_seed=args.plant_seed, sandbox_mode=args.sandbox, profile=profile,
                             eval_plant_factory=eval_factory, operator_disturbance=operator_disturbance)
    orch = Orchestrator(session, store, agent, plant, Supervisor(limits), None, cfg, on_event=on_event)
    lo, hi = profile.band
    print(f"run_id={run_id} model={getattr(agent, 'model', '?')} plant={profile.name} plant_seed={args.plant_seed} "
          f"disturbance={args.disturbance} sandbox={args.sandbox} eval_plant={eval_plant}"
          f"{' operator_disturbance=yes' if operator_disturbance else ''}")
    print(f"profile: {profile.description_for_operator} dt={profile.dt}s units: y normalized "
          f"(display {profile.y_unit} = y*{profile.y_scale:g}+{profile.y_offset:g})")
    print(f"objective: target={profile.target:.4f} band=[{lo:.4f}, {hi:.4f}]"
          + (f" = {profile.to_display(profile.target):.1f} {profile.y_unit} "
             f"[{profile.to_display(lo):.1f}, {profile.to_display(hi):.1f}]" if show_c else "")
          + f"; soft/hard limit {profile.soft_high_limit}/{profile.hard_cutoff}"
          + (f" = {profile.to_display(profile.soft_high_limit):.0f}/{profile.to_display(profile.hard_cutoff):.0f} {profile.y_unit}"
             if show_c else "")
          + f"; episode {profile.episode_s:.0f}s settle {profile.settle_s:.0f}s\n")
    # Hardware safety: whatever ends the process (normal return, Ctrl-C, SIGTERM, a closed terminal
    # window = SIGHUP, or an exception), the actuator is turned off and the port closed.
    def _raise_exit(signum: int, _frame: object) -> None:
        raise SystemExit(128 + signum)

    for sig in (signal.SIGTERM, signal.SIGHUP):
        with contextlib.suppress(Exception):
            signal.signal(sig, _raise_exit)
    try:
        orch.run_discovery()
        if session.stage == "DEPLOYABLE":
            orch.run_monitoring(None if args.disturbance == "none" else args.disturbance)
    finally:
        close = getattr(plant, "close", None)
        if callable(close):
            with contextlib.suppress(Exception):
                close()

    totals = getattr(agent, "totals", None)
    print(f"\nfinal stage: {session.stage}")
    print(f"candidates: {[(c.candidate_id, c.status) for c in session.candidates]}")
    if totals:
        print(f"model calls: {totals.calls} (failed {totals.failed_calls}), tokens in/out/reasoning: "
              f"{totals.prompt_tokens}/{totals.completion_tokens}/{totals.reasoning_tokens}, est. cost ${totals.cost_usd:.3f}")
    print(f"artifacts: {store.dir}")
    return 0 if session.stage in {"COMPLETE", "DEPLOYABLE"} else 1


_Y_KEYS = {"y", "target", "y_mean", "y_start", "y_end", "y_min", "y_max", "y_now", "baseline_window_mae"}


def _with_celsius(payload: dict, profile: PlantProfile) -> dict:
    """Add a °C rendering next to normalized level-like numbers (display only; never sent to the agent)."""
    out = dict(payload)
    for k, v in payload.items():
        if k in _Y_KEYS and isinstance(v, (int, float)) and not isinstance(v, bool):
            if k == "baseline_window_mae":
                out[f"{k}_C"] = round(float(v) * profile.y_scale, 2)  # an error: scale only, no offset
            else:
                out[f"{k}_C"] = round(profile.to_display(float(v)), 2)
    return out


if __name__ == "__main__":
    raise SystemExit(main())
