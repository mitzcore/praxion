"""Measure the self-repair claim directly on the physical TCLab board.

  uv run python scripts/verify_on_board.py --run <run_id> --port /dev/cu.usbmodem1101 --disturbance derate
  uv run python scripts/verify_on_board.py --run <run_id> --port ... --disturbance operator --order v2,v1

Loads the bundle's controller_v1.py and the promoted controller (highest approved version in
result.json), verifies each file's sha256 + length against its meta.json BEFORE anything runs (abort on
mismatch), builds each controller exactly as the orchestrator does (backend.controller.sandbox.make_sandbox,
Docker by default), runs a protocol-matched twin prediction first, then one board trial per controller
(trusted Q1 derate at pre_s, or the operator applies the change by hand), and writes
<run_dir>/board_verification.json plus board_* events appended to the run's event_log.jsonl.

--fake-board (TEST ONLY) replaces the serial board with an in-process thermal model and an accelerated
clock. The output and board_verification.json are labelled fake_board: true. Never use it as evidence.
"""
from __future__ import annotations

import argparse
import contextlib
import hashlib
import json
import math
import signal
import subprocess
import sys
import threading
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.controller.sandbox import docker_available, ensure_image, make_sandbox
from backend.evaluation.board_verify import BoardVerification, run_board_verification
from backend.plant.base import PlantAdapter
from backend.profiles import TCLAB, PlantProfile
from backend.safety.supervisor import SafetyLimits, Supervisor
from backend.schemas import DisturbanceSpec
from backend.storage.artifacts import RunStore

DEFAULT_MAGNITUDE = 0.35


class BundleError(RuntimeError):
    pass


# ------------------------------------------------------------------------------------- bundle
def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def promoted_version(run_dir: Path) -> int:
    """Highest candidate version whose result.json status is 'approved'."""
    result = json.loads((run_dir / "result.json").read_text())
    approved = [int(c["version"]) for c in result.get("candidates") or [] if c.get("status") == "approved"]
    if not approved:
        raise BundleError(f"{run_dir.name}: no approved candidate in result.json")
    return max(approved)


def load_verified_source(run_dir: Path, version: int) -> tuple[str, str, str]:
    """(candidate_id, source, sha256) after checking the file against controller_vN.meta.json."""
    src_p = run_dir / f"controller_v{version}.py"
    meta_p = run_dir / f"controller_v{version}.meta.json"
    if not src_p.exists() or not meta_p.exists():
        raise BundleError(f"v{version}: {src_p.name} or {meta_p.name} missing")
    data = src_p.read_bytes()
    meta = json.loads(meta_p.read_text())
    if _sha(data) != meta.get("sha256") or len(data) != meta.get("byte_length"):
        raise BundleError(f"v{version}: sha256 {_sha(data)} / {len(data)} B does not match meta.json "
                          f"{meta.get('sha256')} / {meta.get('byte_length')} B; refusing to run")
    return str(meta.get("id") or f"{run_dir.name}-v{version}"), data.decode("utf-8"), _sha(data)


def bundle_trials(run_dir: Path, order: list[str], sandbox: str) -> list[tuple[str, Callable[[], Any], str]]:
    """Trials for the requested order. Labels: 'v1' = controller_v1.py, 'v2' = the promoted controller
    (any version >= 2). If only v1 is approved, only 'v1' is kept."""
    top = promoted_version(run_dir)
    versions = {"v1": 1}
    if top >= 2:
        versions["v2"] = top
    out = []
    for label in order:
        if label not in versions:
            continue
        cid, src, sha = load_verified_source(run_dir, versions[label])

        def make(src: str = src, cid: str = cid) -> Any:
            return make_sandbox(src, name=cid, mode=sandbox)  # the orchestrator's _make_controller path

        out.append((label, make, sha))
    if not out:
        raise BundleError(f"no runnable trials for order {order}")
    return out


def build_twin(run_dir: Path, mode: str) -> tuple[Callable[[], PlantAdapter] | None, str | None, str | None]:
    """(factory, prediction_basis, missing_reason)."""
    from backend.plant.thermal_twin import TwinParams, twin_factory

    if mode == "derate":
        name, basis = "twin_fit.json", "original_twin_plus_trusted_derate"
    else:
        # A fan is not reproducible in software: the changed twin runs the WHOLE trial, so its pre window is
        # also the changed machine and only the post-window numbers are the prediction.
        name, basis = "twin_fit_after_change.json", "changed_twin_whole_trial"
    p = run_dir / name
    if not p.exists():
        return None, None, f"{name} missing in bundle; no twin prediction"
    return twin_factory(TwinParams(**json.loads(p.read_text()))), basis, None


def twin_suite_median(run_dir: Path, version: int) -> float | None:
    p = run_dir / f"evaluation_disturbance_v{version}.json"
    if not p.exists():
        return None
    v = (json.loads(p.read_text()).get("aggregate") or {}).get("median_post_disturbance_mae")
    return float(v) if v is not None else None


# ------------------------------------------------------------------------------------- operator hooks
def _alert(message: str, enabled: bool) -> None:
    if not enabled:
        return
    with contextlib.suppress(Exception):
        subprocess.run(["osascript", "-e", f'display notification "{message}" with title "Praxion board"'],
                       check=False, timeout=5, capture_output=True)
    with contextlib.suppress(Exception):
        subprocess.Popen(["say", message], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def _wait_for(trigger: Path) -> None:
    while not trigger.exists():
        time.sleep(0.5)
    with contextlib.suppress(FileNotFoundError):
        trigger.unlink()


def operator_hooks(run_dir: Path, *, alerts: bool = True, auto: bool = False,
                   log: Callable[..., None] | None = None) -> tuple[Callable[[], Callable[[], bool]], Callable[[], None]]:
    """(pause_for_operator, pause_between_trials). Both wait for trigger files in the run dir, like
    Orchestrator._operator_pause without a TTY, and delete the trigger once consumed. A stale trigger left
    from an earlier run is removed before prompting. ``auto`` (fake board only) creates the trigger itself."""
    go, off = run_dir / "OPERATOR_GO", run_dir / "OPERATOR_OFF"

    def pause_for_operator() -> Callable[[], bool]:
        with contextlib.suppress(FileNotFoundError):
            go.unlink()
        msg = "Apply the physical disturbance now"
        print(f"\n>>> {msg}, then create {go} (control keeps running)...", flush=True)
        _alert(msg, alerts)
        if log:
            log("operator_disturbance_prompt", trigger=str(go), purpose="apply")
        done = threading.Event()

        def _w() -> None:
            _wait_for(go)
            done.set()

        if auto:
            go.touch()
        threading.Thread(target=_w, name="board-operator-go", daemon=True).start()
        return done.is_set

    def pause_between_trials() -> None:
        with contextlib.suppress(FileNotFoundError):
            off.unlink()
        msg = "Turn the disturbance OFF before the next trial"
        print(f"\n>>> {msg}, then create {off} (heater is off)...", flush=True)
        _alert(msg, alerts)
        if log:
            log("operator_disturbance_prompt", trigger=str(off), purpose="remove_before_next_trial")
        if auto:
            off.touch()
        _wait_for(off)

    return pause_for_operator, pause_between_trials


# ------------------------------------------------------------------------------------- fake board (TEST ONLY)
class FakeClock:
    """Accelerated clock: sleep() advances time instantly."""

    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now

    def sleep(self, d: float) -> None:
        self.now += max(0.0, float(d))


class FakeThermalLab:
    """TEST ONLY: first-order-plus-lag heater integrated on the fake clock (K 76 °C, tau 175 s, lag 30 s)."""

    def __init__(self, clock: FakeClock, T0: float = 30.0, Ta: float = 22.0, K: float = 76.0, tau: float = 175.0,
                 lag_s: float = 30.0) -> None:
        self.clock, self.Ta, self.K, self.tau = clock, Ta, K, tau
        self.T = T0
        self._t = clock()
        self._q = 0.0
        self._hist: list[tuple[float, float]] = [(self._t, 0.0)]
        self.lag_s = lag_s
        self.q1: list[float] = []
        self.q2: list[float] = []
        self.closed = False

    def _advance(self) -> None:
        now = self.clock()
        while self._t + 1e-9 < now:
            h = min(0.2, now - self._t)
            q = self._q_at(self._t - self.lag_s)
            self.T += h * (self.Ta + self.K * q / 100.0 - self.T) / self.tau
            self._t += h

    def _q_at(self, t: float) -> float:
        q = 0.0
        for ts, v in self._hist:
            if ts <= t + 1e-9:
                q = v
            else:
                break
        return q

    @property
    def T1(self) -> float:
        self._advance()
        return self.T

    def Q1(self, v: float | None = None) -> float:
        if v is not None:
            self._advance()
            self.q1.append(float(v))
            self._hist.append((self.clock(), float(v)))
            if len(self._hist) > 400:
                self._hist = self._hist[-400:]
        return self.q1[-1] if self.q1 else 0.0

    def Q2(self, v: float | None = None) -> float:
        if v is not None:
            self.q2.append(float(v))
        return self.q2[-1] if self.q2 else 0.0

    def close(self) -> None:
        self.closed = True


def fake_board() -> Any:
    from backend.plant.tclab_plant import TCLabHardware

    clk = FakeClock()
    lab = FakeThermalLab(clk)
    return TCLabHardware(port="FAKE", lab_factory=lambda: lab, clock=clk, sleep=clk.sleep)


# ------------------------------------------------------------------------------------- run + report
def run_verification(run_dir: Path, plant: PlantAdapter, *, mode: str, order: list[str], sandbox: str,
                     magnitude: float = DEFAULT_MAGNITUDE, pre_s: float = 480.0, post_s: float = 600.0,
                     profile: PlantProfile = TCLAB, fake: bool = False, alerts: bool = True,
                     quiet: bool = False) -> BoardVerification:
    """Shared by this script and run_live_demo --verify-on-board. Writes board_verification.json and
    appends events (stage = the run's final stage from result.json) through RunStore."""
    run_dir = Path(run_dir)
    trials = bundle_trials(run_dir, order, sandbox)  # hashes verified here, before anything runs
    result = json.loads((run_dir / "result.json").read_text())
    stage = str(result.get("stage") or "COMPLETE")
    store = RunStore(run_dir.name, root=run_dir.parent)
    t0 = time.time()

    def log(kind: str, **payload: Any) -> None:
        payload.setdefault("fake_board", fake)
        store.event(kind, stage=stage, **payload)
        if not quiet:
            short = {k: v for k, v in payload.items() if k not in ("trials", "prediction_vs_board")}
            print(f"[{time.time() - t0:6.1f}s] {kind:24s} {json.dumps(short, default=str)[:240]}", flush=True)

    if mode == "derate":
        dist: DisturbanceSpec | None = DisturbanceSpec(family="pump_derate", at_t=float(pre_s), magnitude=float(magnitude))
        pause_go = pause_off = None
    else:
        dist = None
        pause_go, pause_off = operator_hooks(run_dir, alerts=alerts and not fake, auto=fake, log=log)
    twin, basis, missing = build_twin(run_dir, mode)
    sup = Supervisor(SafetyLimits.from_profile(profile))
    bv = run_board_verification(
        plant, trials, supervisor=sup, profile=profile, pre_s=pre_s, post_s=post_s, disturbance=dist,
        pause_for_operator=pause_go, pause_between_trials=pause_off, on_event=log,
        twin_factory=twin, prediction_basis=basis, twin_missing_reason=missing,
    )
    bv.fake_board = fake
    store.write_json("board_verification.json", bv.model_dump(mode="json"))
    if mode == "operator":
        msg = "Session complete: turn the disturbance OFF now"
        print(f"\n>>> {msg} (heater is off, nothing more to trigger).", flush=True)
        _alert(msg, alerts and not fake)
    return bv


def _fmt(x: float | None, scale: float = 1.0, nd: int = 4) -> str:
    if x is None or not isinstance(x, (int, float)) or not math.isfinite(x):
        return "-"
    return f"{x * scale:.{nd}f}"


def format_table(run_dir: Path, bv: BoardVerification, profile: PlantProfile = TCLAB) -> str:
    top = promoted_version(run_dir)
    vers = {"v1": 1, "v2": top}
    pred = {t["label"]: t for t in (bv.twin_prediction or {}).get("trials", [])}
    s = profile.y_scale
    lines = []
    if bv.fake_board:
        lines.append("*** FAKE BOARD (test only): in-process thermal model, accelerated clock. NOT EVIDENCE. ***")
    lines.append(f"board verification: {run_dir.name}  order={','.join(bv.order)}  pre_s={bv.pre_s:.0f} "
                 f"post_s={bv.post_s:.0f}  disturbance={bv.disturbance}")
    lines.append("post-change MAE (normalized y | °C)")
    lines.append(f"{'ctrl':5s} {'suite median (twin)':>22s} {'twin, this protocol':>22s} {'BOARD measured':>22s} "
                 f"{'in-band':>8s} {'ovr':>4s} {'viol':>4s} {'trip':>5s} {'start °C':>8s}")
    for t in bv.trials:
        sm = twin_suite_median(run_dir, vers.get(t.label, 0))
        pm = pred.get(t.label, {}).get("post_mae")
        lines.append(
            f"{t.label:5s} {_fmt(sm):>10s} | {_fmt(sm, s, 2):>8s}  {_fmt(pm):>10s} | {_fmt(pm, s, 2):>8s}  "
            f"{_fmt(t.post_mae):>10s} | {_fmt(t.post_mae, s, 2):>8s}  {_fmt(t.post_in_band, 1, 3):>8s} "
            f"{t.overrides:>4d} {t.hard_violations:>4d} {t.interlock_hit!s:>5s} {t.start_T_display:8.1f}")
    if bv.comparison:
        c = bv.comparison
        lines.append(f"board: v1 -> v2 post-change MAE reduction {_fmt(c.get('reduction'), 100, 1)} %")
    if bv.twin_prediction:
        pc = bv.twin_prediction.get("comparison") or {}
        lines.append(f"twin ({bv.twin_prediction.get('prediction_basis')}): predicted reduction "
                     f"{_fmt(pc.get('reduction'), 100, 1)} %; direction agrees with board: "
                     f"{(bv.prediction_vs_board or {}).get('direction_agrees')}")
    else:
        lines.append(f"twin prediction: none ({bv.twin_prediction_reason})")
    lines.append(f"written: {run_dir / 'board_verification.json'}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--run", required=True)
    ap.add_argument("--root", default="artifacts/runs")
    ap.add_argument("--port", default=None)
    ap.add_argument("--disturbance", choices=["derate", "operator"], required=True)
    ap.add_argument("--magnitude", type=float, default=DEFAULT_MAGNITUDE)
    ap.add_argument("--order", choices=["v1,v2", "v2,v1"], default="v1,v2")
    ap.add_argument("--pre-s", type=float, default=480.0)
    ap.add_argument("--post-s", type=float, default=600.0)
    ap.add_argument("--sandbox", choices=["docker", "subprocess_dev_only"], default="docker")
    ap.add_argument("--fake-board", action="store_true", help="TEST ONLY: in-process fake board, accelerated clock")
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args(argv)

    run_dir = Path(args.root) / args.run
    if not (run_dir / "result.json").exists():
        print(f"error: {run_dir}/result.json not found", file=sys.stderr)
        return 2
    order = args.order.split(",")
    try:
        bundle_trials(run_dir, order, args.sandbox)  # verify hashes before touching the board or Docker
    except BundleError as e:
        print(f"error: {e}", file=sys.stderr)
        return 3
    if args.sandbox == "docker":
        if not docker_available():
            print("Docker is not available; use --sandbox subprocess_dev_only for development only.", file=sys.stderr)
            return 2
        ensure_image()
    if args.fake_board:
        plant: Any = fake_board()
        print("*** --fake-board: TEST ONLY, no hardware; results are labelled fake_board=true ***")
    else:
        if not args.port:
            print("error: --port is required (or --fake-board for tests)", file=sys.stderr)
            return 2
        from backend.plant.tclab_plant import TCLabHardware

        plant = TCLabHardware(port=args.port)

    def _raise_exit(signum: int, _frame: object) -> None:
        raise SystemExit(128 + signum)

    for sig in (signal.SIGTERM, signal.SIGHUP):
        with contextlib.suppress(Exception):
            signal.signal(sig, _raise_exit)
    try:
        bv = run_verification(run_dir, plant, mode=args.disturbance, order=order, sandbox=args.sandbox,
                              magnitude=args.magnitude, pre_s=args.pre_s, post_s=args.post_s,
                              fake=args.fake_board, quiet=args.quiet)
    except BundleError as e:
        print(f"error: {e}", file=sys.stderr)
        return 3
    finally:
        with contextlib.suppress(Exception):
            plant.emergency_stop()
        with contextlib.suppress(Exception):
            plant.close()
    print()
    print(format_table(run_dir, bv))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
