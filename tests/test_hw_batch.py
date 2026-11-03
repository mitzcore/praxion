"""scripts/run_hw_batch.py: ordering, summary JSON, 2-failure stop rule, watchdog. No board, no API."""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location("run_hw_batch", ROOT / "scripts" / "run_hw_batch.py")
hb = importlib.util.module_from_spec(_spec)
sys.modules["run_hw_batch"] = hb
_spec.loader.exec_module(hb)


def _stub(tmp: Path, body: str) -> Path:
    p = tmp / "stub_child.py"
    p.write_text(body)
    return p


OK_STUB = """import sys, time
label = sys.argv[sys.argv.index('--label') + 1]
order = sys.argv[sys.argv.index('--order') + 1]
print(f'run_id={label}-stub order={order}', flush=True)
time.sleep(0.1)
print('final stage: COMPLETE')
"""

CRASH_STUB = """import sys
print('run_id=crash-stub', flush=True)
raise RuntimeError('plant fault: serial port vanished')
"""

GATE_FAIL_STUB = """import sys
print('run_id=gate-stub', flush=True)
print('final stage: FAILED')
sys.exit(1)
"""

SLEEP_STUB = """import time
print('run_id=slow-stub', flush=True)
time.sleep(30)
print('final stage: COMPLETE')
"""


def _args(tmp: Path, stub: Path, n: int, max_run_s: float = 60.0):
    cmd = f"{sys.executable} {stub} --label {{label}} --order {{order}}"
    return hb.parse_args(["--n", str(n), "--command", cmd, "--root", str(tmp / "runs"), "--log",
                          str(tmp / "logs" / "hw_batch.log"), "--max-run-s", str(max_run_s), "--no-caffeinate"])


@pytest.fixture
def calls():
    rec: dict[str, list] = {"off": [], "cool": []}

    def off(port):
        rec["off"].append(port)
        return True

    def cool(port, below, timeout):
        rec["cool"].append((port, below, timeout))
        return 41.5

    rec["off_fn"], rec["cool_fn"] = off, cool
    return rec


def _run(args, calls):
    return hb.run_batch(args, heaters_off_fn=calls["off_fn"], cool_down_fn=calls["cool_fn"])


def test_order_alternates():
    assert [hb.order_for(k) for k in range(1, 6)] == ["v1,v2", "v2,v1", "v1,v2", "v2,v1", "v1,v2"]


def test_batch_summary_and_ordering(tmp_path, calls):
    s = _run(_args(tmp_path, _stub(tmp_path, OK_STUB), 3), calls)
    assert [r["order"] for r in s["runs"]] == ["v1,v2", "v2,v1", "v1,v2"]
    assert [r["run_id"] for r in s["runs"]] == ["hwb1-stub", "hwb2-stub", "hwb3-stub"]
    assert all(r["final_stage"] == "COMPLETE" and r["exit_code"] == 0 and not r["child_failure"] for r in s["runs"])
    assert all(r["cooldown_start_T1_c"] == 41.5 for r in s["runs"])
    assert len(calls["cool"]) == 3 and len(calls["off"]) == 3  # heaters off after every child exit
    files = list((tmp_path / "logs").glob("hw_batch_*.json"))
    assert len(files) == 1
    on_disk = json.loads(files[0].read_text())
    assert on_disk["runs"] == s["runs"] and on_disk["stopped_early"] is False
    assert (tmp_path / "logs" / "hwb2.log").read_text().count("order=v2,v1") == 1


def test_two_consecutive_failures_stop(tmp_path, calls):
    s = _run(_args(tmp_path, _stub(tmp_path, CRASH_STUB), 5), calls)
    assert len(s["runs"]) == 2 and s["stopped_early"]
    assert all(r["child_failure"] for r in s["runs"])
    assert len(calls["off"]) == 2


def test_gate_failure_is_a_result_not_a_batch_failure(tmp_path, calls):
    s = _run(_args(tmp_path, _stub(tmp_path, GATE_FAIL_STUB), 3), calls)
    assert len(s["runs"]) == 3 and not s["stopped_early"]
    assert all(r["final_stage"] == "FAILED" and r["exit_code"] == 1 and not r["child_failure"] for r in s["runs"])


def test_watchdog_kills_and_turns_heaters_off(tmp_path, calls):
    s = _run(_args(tmp_path, _stub(tmp_path, SLEEP_STUB), 1, max_run_s=1), calls)
    r = s["runs"][0]
    assert r["killed"] and r["child_failure"] and r["final_stage"] is None and r["run_id"] == "slow-stub"
    assert r["duration_s"] < 25
    assert calls["off"] == [s["port"]]


def test_dry_run_prints_commands(capsys):
    assert hb.main(["--n", "2", "--dry-run"]) == 0
    out = capsys.readouterr().out.splitlines()
    assert len(out) == 2
    assert "--verify-on-board v1,v2" in out[0] and "--label hwb1" in out[0]
    assert "--verify-on-board v2,v1" in out[1] and "--label hwb2" in out[1]
    assert "--disturbance-applied-by trusted" in out[0]
    assert "--magnitude 0.35" in out[0]


def test_classify_model_api_failure_is_infrastructure():
    failed, why = hb.classify(1, False, "FAILED", "", "model error: structured call failed after 4 attempts: APITimeoutError: Request timed out.")
    assert failed and why.startswith("FAILED:")
    failed, why = hb.classify(1, False, "FAILED", "", "adaptation attempts exhausted; last approved controller retained")
    assert not failed and "measured outcome" in why
