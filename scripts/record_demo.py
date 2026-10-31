"""Record the demo video of one recorded run by driving the real dashboard in headless Chromium.

  uv run python scripts/record_demo.py --run <run_id> [--out artifacts/demo/<run_id>] [--segments default]
                                       [--speed-a 4] [--speed-b 16] [--max-length 240] [--headful]

Starts the API (serving frontend/dist) on a free port, runs scripts/audit_run.py and captures its
stdout, runs scripts/record_demo.mjs (Playwright), stops the server, and prints the video length.
Outputs under --out: demo.webm, sNN_<script time>_<title>[_<view>].png, audit.png, audit.txt,
segments.json. See docs/DEMO_RECORDING.md.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FRONTEND = ROOT / "frontend"

# Rough fixed costs of the recorder outside the replay itself (seconds of footage).
PASS_A_OVERHEAD_S = 10.0
CLOSEUPS_S = 48.0
PER_EXTRA_VERSION_S = 5.0


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def wait_health(base: str, timeout: float = 60.0) -> None:
    end = time.time() + timeout
    while time.time() < end:
        try:
            with urllib.request.urlopen(f"{base}/health", timeout=2) as r:
                if r.status == 200:
                    return
        except OSError:
            pass
        time.sleep(0.3)
    raise RuntimeError(f"API did not become healthy at {base}")


def run_timing(run_dir: Path) -> dict:
    evs = [json.loads(x) for x in (run_dir / "event_log.jsonl").read_text().splitlines() if x.strip()]
    t0 = evs[0]["ts"]
    gen = next((e["ts"] - t0 for e in evs if e.get("kind") == "stage" and e.get("to") == "GENERATING"), None)
    n_versions = sum(1 for e in evs if e.get("kind") == "candidate_registered")
    return {"total_s": evs[-1]["ts"] - t0, "generating_s": gen, "n_versions": n_versions}


def estimate(t: dict, a: float, b: float) -> float:
    gen = t["generating_s"] if t["generating_s"] is not None else t["total_s"]
    return (gen / a + PASS_A_OVERHEAD_S + t["total_s"] / b + CLOSEUPS_S
            + PER_EXTRA_VERSION_S * max(0, t["n_versions"] - 2))


def choose_speeds(t: dict, a: float, b: float, max_len: float) -> tuple[float, float, str | None]:
    """Keep the scripted speeds if the footage fits; otherwise raise the exploration speed first."""
    est0 = estimate(t, a, b)
    if est0 <= max_len:
        return a, b, None
    a2, b2 = a, b
    for cand in (6, 8, 12, 16, 24, 32):
        if cand > a2:
            a2 = float(cand)
            if estimate(t, a2, b2) <= max_len:
                break
    while estimate(t, a2, b2) > max_len and b2 < 64:
        b2 *= 2
    note = (f"scripted speeds {a:g}x/{b:g}x would give ~{est0:.0f} s (> {max_len:.0f} s); "
            f"recorded at {a2:g}x for exploration and {b2:g}x afterwards (estimated {estimate(t, a2, b2):.0f} s)")
    return a2, b2, note


def video_length(path: Path) -> float | None:
    if not shutil.which("ffprobe"):
        return None
    try:
        out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
                             check=False, capture_output=True, text=True, timeout=60).stdout.strip()
        if out and out != "N/A":
            return float(out)
        # webm from Chromium often lacks a container duration; decode to find it
        out = subprocess.run(["ffprobe", "-v", "error", "-count_packets", "-select_streams", "v:0", "-show_entries",
                              "stream=nb_read_packets,r_frame_rate", "-of", "json", str(path)],
                             check=False, capture_output=True, text=True, timeout=300).stdout
        st = json.loads(out)["streams"][0]
        num, den = (int(x) for x in st["r_frame_rate"].split("/"))
        return int(st["nb_read_packets"]) * den / num
    except (OSError, ValueError, KeyError, IndexError, subprocess.SubprocessError):
        return None


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--run", required=True)
    ap.add_argument("--out", default=None)
    ap.add_argument("--segments", default="default")
    ap.add_argument("--root", default=os.getenv("PRAXION_ARTIFACT_ROOT", "artifacts/runs"))
    ap.add_argument("--speed-a", type=float, default=4.0, help="pass A (discovery) speed, script: 4x")
    ap.add_argument("--speed-b", type=float, default=16.0, help="pass B (authoring onward) speed, script: 16x")
    ap.add_argument("--max-length", type=float, default=230.0, help="target video length in seconds (< 4 min)")
    ap.add_argument("--headful", action="store_true")
    args = ap.parse_args()

    run_dir = (ROOT / args.root / args.run) if not Path(args.root).is_absolute() else Path(args.root) / args.run
    if not (run_dir / "event_log.jsonl").exists():
        print(f"no event log at {run_dir}", file=sys.stderr)
        return 2
    out = Path(args.out) if args.out else ROOT / "artifacts" / "demo" / args.run
    out = out if out.is_absolute() else ROOT / out
    out.mkdir(parents=True, exist_ok=True)
    for old in list(out.glob("s[0-9][0-9]_*.png")) + [out / n for n in ("audit.png", "demo.webm", "segments.json")]:
        old.unlink(missing_ok=True)

    if not (FRONTEND / "dist" / "index.html").exists():
        print("frontend/dist missing; building", flush=True)
        subprocess.run(["npm", "install"], cwd=FRONTEND, check=True)
        subprocess.run(["npm", "run", "build"], cwd=FRONTEND, check=True)
    if not (FRONTEND / "node_modules" / "playwright").exists():
        print("playwright missing; installing frontend devDependencies and chromium", flush=True)
        subprocess.run(["npm", "install"], cwd=FRONTEND, check=True)
        subprocess.run(["npx", "playwright", "install", "chromium"], cwd=FRONTEND, check=True)

    t = run_timing(run_dir)
    speed_a, speed_b, note = choose_speeds(t, args.speed_a, args.speed_b, args.max_length)
    print(f"run {args.run}: {t['total_s']:.0f} s at 1x, GENERATING at {t['generating_s']} s, "
          f"{t['n_versions']} controller version(s)")
    print(f"speeds: pass A {speed_a:g}x, pass B {speed_b:g}x; estimated footage {estimate(t, speed_a, speed_b):.0f} s"
          + (f"\nNOTE: {note}" if note else ""), flush=True)

    # Audit first (pure read of the bundle); stdout is rendered verbatim at the end of the video.
    root_arg = [] if args.root == "artifacts/runs" else ["--root", args.root]
    audit_cmd = " ".join(["uv run python scripts/audit_run.py", args.run, *root_arg])
    audit = subprocess.run([sys.executable, str(ROOT / "scripts" / "audit_run.py"), args.run, "--root", str(run_dir.parent)],
                           check=False, cwd=ROOT, capture_output=True, text=True)
    (out / "audit.txt").write_text(audit.stdout)
    print(f"audit exit {audit.returncode}: "
          f"{next((x for x in audit.stdout.splitlines() if x.startswith('RESULT:')), 'no RESULT line')}", flush=True)

    port = free_port()
    base = f"http://127.0.0.1:{port}"
    env = {**os.environ, "PRAXION_ARTIFACT_ROOT": str(run_dir.parent)}
    env.pop("PRAXION_REPLAY_RUN", None)
    server = subprocess.Popen([sys.executable, "-m", "uvicorn", "backend.main:app", "--host", "127.0.0.1",
                               "--port", str(port), "--log-level", "warning"], cwd=ROOT, env=env)
    try:
        wait_health(base)
        cmd = ["node", str(ROOT / "scripts" / "record_demo.mjs"), "--base", base, "--run", args.run, "--out", str(out),
               "--audit", str(out / "audit.txt"), "--speed-a", f"{speed_a:g}", "--speed-b", f"{speed_b:g}",
               "--segments", args.segments, "--audit-cmd", audit_cmd]
        if note:
            cmd += ["--speed-note", note]
        if args.headful:
            cmd.append("--headful")
        rc = subprocess.run(cmd, check=False, cwd=ROOT).returncode
    finally:
        server.terminate()
        try:
            server.wait(timeout=10)
        except subprocess.TimeoutExpired:
            server.kill()
    if rc != 0:
        print(f"recorder failed (exit {rc})", file=sys.stderr)
        return rc

    webm = out / "demo.webm"
    length = video_length(webm)
    seg_path = out / "segments.json"
    seg = json.loads(seg_path.read_text())
    seg["video_length_s"] = round(length, 2) if length is not None else None
    seg_path.write_text(json.dumps(seg, indent=2))

    print("\nproduced:")
    for p in sorted(out.iterdir()):
        if p.is_file():
            print(f"  {p.stat().st_size:>10,d}  {p.relative_to(ROOT) if p.is_relative_to(ROOT) else p}")
    clock = seg.get("recorder_clock_length_s")
    if length is not None:
        print(f"\nvideo length: {length:.1f} s ({int(length // 60)}:{length % 60:04.1f})  [recorder clock {clock} s]")
    else:
        print(f"\nvideo length (recorder clock, ffprobe unavailable): {clock} s")
    issues = [f"{s['id']}: {i}" for s in seg["segments"] for i in s["issues"]]
    print("segment issues:" if issues else "segment issues: none")
    for i in issues:
        print(f"  - {i}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
