"""Run N sequential, unattended hardware runs on the physical TCLab board (overnight batch).

  uv run python scripts/run_hw_batch.py --n 6 --port /dev/cu.usbmodem1101
  uv run python scripts/run_hw_batch.py --n 2 --dry-run          # print the commands and exit

Per run k (1-based):
  (a) heaters off + cool-down: open the board, Q1(0)/Q2(0), poll T1 every 10 s until T1 < --cool-below-c
      or --cool-timeout-s, log the readings, close the port (the child process needs it);
  (b) counterbalance the on-board verification order: odd k -> v1,v2; even k -> v2,v1;
  (c) run the child under a wall-clock watchdog (--max-run-s; killed on timeout), stdout/stderr to
      artifacts/batch_logs/<label>.log;
  (d) heaters off again after every child exit (retry 5x, 2 s apart: the port may be briefly busy);
  (e) stop after 2 consecutive child failures, and always write/print the batch summary.

A "child failure" is an infrastructure failure: watchdog kill, a non-zero exit with no `final stage:`
line (crash), or `final stage: FAILED` whose reason is an unexpected error / plant fault. A clean
`final stage: FAILED` because no candidate passed the release gate is a measured result, not a
failure of the batch, and does not count toward the stop rule (run_live_demo.py exits 1 for both,
so the exit code alone cannot tell them apart).

The whole batch runs under `caffeinate -dims` (a sibling process, terminated at the end). Standard
library only; tclab/pyserial are imported lazily so --dry-run and the tests need no board.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import time
from collections.abc import Callable
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

DEFAULT_COMMAND = (
    "uv run python scripts/run_live_demo.py --plant tclab --port {port} --disturbance {disturbance} "
    "--disturbance-applied-by trusted --verify-on-board {order} --label {label} --root {root} --quiet"
)
_RUN_ID_RE = re.compile(r"^run_id=(\S+)", re.MULTILINE)
_STAGE_RE = re.compile(r"^final stage:\s*(\S+)", re.MULTILINE)
_FAULT_RE = re.compile(
    r"unexpected error|plant fault|PlantUnavailable|SerialException|could not open port|"
    r"Traceback \(most recent call last\)",
    re.IGNORECASE,
)

_LOG_PATH: Path | None = None


def log(msg: str) -> None:
    line = f"[{datetime.now().isoformat(timespec='seconds')}] {msg}"
    print(line, flush=True)
    if _LOG_PATH is not None:
        _LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with _LOG_PATH.open("a", encoding="utf-8") as f:
            f.write(line + "\n")


# ---------------------------------------------------------------- hardware (lazy imports)

def _open_board(port: str):
    import tclab  # lazy: not needed for --dry-run or tests

    return tclab.TCLab(port=port)


def heaters_off(port: str, retries: int = 5, sleep_s: float = 2.0) -> bool:
    """Q1(0), Q2(0), close. Retries because the child may still be releasing the serial port."""
    for attempt in range(1, retries + 1):
        try:
            lab = _open_board(port)
            try:
                lab.Q1(0)
                lab.Q2(0)
                t1 = lab.T1
            finally:
                lab.close()
            log(f"heaters off (attempt {attempt}); T1={t1:.2f} C")
            return True
        except Exception as e:  # noqa: BLE001 - any serial/board error is retried, then reported
            log(f"heaters-off attempt {attempt}/{retries} failed: {type(e).__name__}: {e}")
            if attempt < retries:
                time.sleep(sleep_s)
    log("WARNING: heaters-off failed after all retries")
    return False


def cool_down(port: str, below_c: float, timeout_s: float, poll_s: float = 10.0) -> float | None:
    """Heaters off, then poll T1 until it drops below `below_c` or the timeout. Returns the start T1."""
    lab = None
    for attempt in range(1, 6):
        try:
            lab = _open_board(port)
            break
        except Exception as e:  # noqa: BLE001
            log(f"cool-down: open attempt {attempt}/5 failed: {type(e).__name__}: {e}")
            time.sleep(2.0)
    if lab is None:
        log("WARNING: cool-down skipped: board could not be opened")
        return None
    try:
        lab.Q1(0)
        lab.Q2(0)
        t_start = float(lab.T1)
        log(f"cool-down start: T1={t_start:.2f} C (target < {below_c:.1f} C, timeout {timeout_s:.0f} s)")
        t0 = time.monotonic()
        t1 = t_start
        while t1 >= below_c and time.monotonic() - t0 < timeout_s:
            time.sleep(poll_s)
            t1 = float(lab.T1)
            log(f"cool-down: t={time.monotonic() - t0:5.0f}s T1={t1:.2f} C")
        if t1 < below_c:
            log(f"cool-down done: T1={t1:.2f} C after {time.monotonic() - t0:.0f} s")
        else:
            log(f"cool-down TIMEOUT: T1={t1:.2f} C after {timeout_s:.0f} s; proceeding")
        return t_start
    finally:
        try:
            lab.Q1(0)
            lab.Q2(0)
            lab.close()
        except Exception as e:  # noqa: BLE001
            log(f"cool-down: close failed: {type(e).__name__}: {e}")


# ---------------------------------------------------------------- batch logic

def order_for(k: int) -> str:
    """Counterbalanced verification order: odd runs v1 first, even runs v2 first."""
    return "v1,v2" if k % 2 == 1 else "v2,v1"


def build_command(template: str, *, port: str, disturbance: str, magnitude: float, order: str, label: str,
                  root: str) -> list[str]:
    return shlex.split(template.format(port=port, disturbance=disturbance, magnitude=magnitude, order=order,
                                       label=label, root=root))


def _final_reason(root: Path, run_id: str | None) -> str | None:
    if not run_id:
        return None
    p = root / run_id / "result.json"
    try:
        hist = json.loads(p.read_text()).get("stage_history") or []
        return (hist[-1] or {}).get("reason") if hist else None
    except (OSError, ValueError):
        return None


def classify(exit_code: int | None, killed: bool, stage: str | None, log_text: str, reason: str | None) -> tuple[bool, str]:
    """(is_failure, why). See the module docstring for the definition of a child failure."""
    if killed:
        return True, "watchdog kill"
    if stage is None:
        return (exit_code != 0), ("no final stage line (crash)" if exit_code != 0 else "no final stage line")
    if stage == "FAILED":
        if reason and _FAULT_RE.search(reason):
            return True, f"FAILED: {reason}"
        if _FAULT_RE.search(log_text):
            return True, "FAILED with unexpected error / plant fault in log"
        return False, f"FAILED (measured outcome): {reason or 'gate'}"
    if exit_code not in (0, None) and stage not in {"COMPLETE", "DEPLOYABLE"}:
        return True, f"exit {exit_code} at stage {stage}"
    return False, "ok"


def run_child(cmd: list[str], log_file: Path, max_run_s: float, cwd: Path) -> tuple[int | None, bool, float, str]:
    """Run with a watchdog. Returns (exit_code, killed, duration_s, captured_text)."""
    log_file.parent.mkdir(parents=True, exist_ok=True)
    t0 = time.monotonic()
    killed = False
    with log_file.open("w", encoding="utf-8") as f:
        f.write(f"# command: {shlex.join(cmd)}\n# started: {datetime.now().isoformat(timespec='seconds')}\n")
        f.flush()
        proc = subprocess.Popen(cmd, stdout=f, stderr=subprocess.STDOUT, cwd=str(cwd), start_new_session=True)
        try:
            code: int | None = proc.wait(timeout=max_run_s)
        except subprocess.TimeoutExpired:
            killed = True
            log(f"WATCHDOG: child exceeded {max_run_s:.0f} s; sending SIGTERM")
            _kill_tree(proc)
            code = proc.returncode
        f.write(f"\n# exit: {code} killed={killed} duration_s={time.monotonic() - t0:.1f}\n")
    return code, killed, time.monotonic() - t0, log_file.read_text(encoding="utf-8", errors="replace")


def _kill_tree(proc: subprocess.Popen) -> None:
    import signal

    for sig, wait in ((signal.SIGTERM, 20.0), (signal.SIGKILL, 10.0)):
        try:
            os.killpg(proc.pid, sig)
        except (ProcessLookupError, PermissionError):
            pass
        try:
            proc.wait(timeout=wait)
            return
        except subprocess.TimeoutExpired:
            continue


def start_caffeinate(enabled: bool) -> subprocess.Popen | None:
    if not enabled:
        return None
    exe = shutil.which("caffeinate")
    if not exe:
        log("caffeinate not found; continuing without it")
        return None
    p = subprocess.Popen([exe, "-dims", "-w", str(os.getpid())])
    log(f"caffeinate -dims started (pid {p.pid})")
    return p


def run_batch(args: argparse.Namespace, *, heaters_off_fn: Callable[[str], bool] = heaters_off,
              cool_down_fn: Callable[[str, float, float], float | None] = cool_down) -> dict:
    root = Path(args.root)
    logs_dir = Path(args.log).parent
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    summary_path = logs_dir / f"hw_batch_{stamp}.json"
    summary: dict = {
        "started": datetime.now().isoformat(timespec="seconds"), "n_requested": args.n, "port": args.port,
        "disturbance": args.disturbance, "magnitude": args.magnitude,
        "magnitude_passed_to_child": "{magnitude}" in args.command, "command_template": args.command,
        "max_run_s": args.max_run_s, "cool_below_c": args.cool_below_c, "cool_timeout_s": args.cool_timeout_s,
        "runs": [], "stopped_early": False, "stop_reason": None,
    }
    if not summary["magnitude_passed_to_child"]:
        log(f"note: --magnitude {args.magnitude} is recorded but the command template has no {{magnitude}} placeholder")

    def write_summary() -> None:
        summary_path.parent.mkdir(parents=True, exist_ok=True)
        summary_path.write_text(json.dumps(summary, indent=2))

    consecutive = 0
    caff = start_caffeinate(not args.no_caffeinate)
    try:
        for k in range(1, args.n + 1):
            label = f"{args.label_prefix}{k}"
            order = order_for(k)
            cmd = build_command(args.command, port=args.port, disturbance=args.disturbance,
                                magnitude=args.magnitude, order=order, label=label, root=args.root)
            log(f"=== run {k}/{args.n} label={label} order={order}")
            cool_t = cool_down_fn(args.port, args.cool_below_c, args.cool_timeout_s)
            log(f"exec: {shlex.join(cmd)}")
            code, killed, dur, text = run_child(cmd, logs_dir / f"{label}.log", args.max_run_s, ROOT)
            heaters_off_fn(args.port)
            m_id, m_stage = _RUN_ID_RE.search(text), _STAGE_RE.search(text)
            run_id = m_id.group(1) if m_id else None
            stage = m_stage.group(1) if m_stage else None
            reason = _final_reason(root, run_id)
            failed, why = classify(code, killed, stage, text, reason)
            consecutive = consecutive + 1 if failed else 0
            rec = {"k": k, "label": label, "order": order, "run_id": run_id, "exit_code": code, "killed": killed,
                   "final_stage": stage, "final_reason": reason, "child_failure": failed, "classification": why,
                   "duration_s": round(dur, 1), "cooldown_start_T1_c": cool_t,
                   "log": str(logs_dir / f"{label}.log")}
            summary["runs"].append(rec)
            write_summary()
            log(f"run {k} done: run_id={run_id} exit={code} killed={killed} stage={stage} "
                f"duration={dur:.0f}s -> {why}")
            if consecutive >= 2:
                summary["stopped_early"] = True
                summary["stop_reason"] = f"2 consecutive child failures (runs {k - 1}, {k})"
                log(f"STOP: {summary['stop_reason']}")
                break
    finally:
        summary["finished"] = datetime.now().isoformat(timespec="seconds")
        write_summary()
        if caff is not None:
            caff.terminate()
            try:
                caff.wait(timeout=5)
            except subprocess.TimeoutExpired:
                caff.kill()
            log("caffeinate stopped")
        _print_summary(summary, summary_path)
    return summary


def _print_summary(summary: dict, path: Path) -> None:
    log(f"batch summary -> {path}")
    for r in summary["runs"]:
        log(f"  {r['label']:8s} order={r['order']} run_id={r['run_id']} exit={r['exit_code']} "
            f"stage={r['final_stage']} {r['duration_s']:.0f}s cool_T1={r['cooldown_start_T1_c']} [{r['classification']}]")
    n_ok = sum(1 for r in summary["runs"] if not r["child_failure"])
    log(f"  {len(summary['runs'])}/{summary['n_requested']} runs executed, {n_ok} without infrastructure failure"
        + (f"; stopped early: {summary['stop_reason']}" if summary["stopped_early"] else ""))


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--n", type=int, default=6)
    ap.add_argument("--port", default="/dev/cu.usbmodem1101")
    ap.add_argument("--label-prefix", default="hwb")
    ap.add_argument("--disturbance", default="pump_derate")
    ap.add_argument("--magnitude", type=float, default=0.35,
                    help="recorded in the summary; reaches the child only via a {magnitude} placeholder")
    ap.add_argument("--cool-below-c", type=float, default=30.0)
    ap.add_argument("--cool-timeout-s", type=float, default=900.0)
    ap.add_argument("--max-run-s", type=float, default=12600.0, help="per-run watchdog (default 3.5 h)")
    ap.add_argument("--root", default="artifacts/runs")
    ap.add_argument("--log", default="artifacts/batch_logs/hw_batch.log")
    ap.add_argument("--command", default=DEFAULT_COMMAND,
                    help="child command template; placeholders {port} {disturbance} {magnitude} {order} {label} {root}")
    ap.add_argument("--no-caffeinate", action="store_true")
    ap.add_argument("--dry-run", action="store_true", help="print the commands and exit")
    return ap.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    global _LOG_PATH
    args = parse_args(argv)
    if args.dry_run:
        for k in range(1, args.n + 1):
            cmd = build_command(args.command, port=args.port, disturbance=args.disturbance, magnitude=args.magnitude,
                                order=order_for(k), label=f"{args.label_prefix}{k}", root=args.root)
            print(f"run {k}: cool-down (T1 < {args.cool_below_c} C, <= {args.cool_timeout_s:.0f} s) -> "
                  f"{shlex.join(cmd)}  [watchdog {args.max_run_s:.0f} s, log "
                  f"{Path(args.log).parent / (args.label_prefix + str(k))}.log]")
        return 0
    _LOG_PATH = Path(args.log)
    summary = run_batch(args)
    return 1 if summary["stopped_early"] else 0


if __name__ == "__main__":
    sys.exit(main())
