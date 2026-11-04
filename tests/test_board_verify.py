"""Trusted actuator derate on TCLabHardware, on-board verification (fake board, accelerated clock),
verify_on_board.py hash check, and audit_run.py's board_verification check."""
from __future__ import annotations

import hashlib
import importlib.util
import json
import shutil
import sys
from pathlib import Path

import pytest

from backend.evaluation.board_verify import run_board_verification
from backend.plant.thermal_twin import TwinParams, twin_factory
from backend.profiles import TCLAB
from backend.safety.supervisor import SafetyLimits, Supervisor
from backend.schemas import DisturbanceSpec
from tests.test_tclab_plant import _hw

ROOT = Path(__file__).resolve().parents[1]
HW2 = ROOT / "artifacts" / "runs" / "hw2-20261103-074537-698ba8"


def _load(name: str):
    spec = importlib.util.spec_from_file_location(f"praxion_{name}", ROOT / "scripts" / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


vob = _load("verify_on_board")
audit_run = _load("audit_run")


# ------------------------------------------------------------------ Part A: trusted derate
def test_hw_pump_derate_scales_q1_from_at_t():
    hw, lab, _ = _hw()
    hw.reset(0)
    hw.schedule_disturbance(DisturbanceSpec(family="pump_derate", at_t=3.0))
    assert hw.applied_disturbances == [{"family": "pump_derate", "at_t": 3.0, "magnitude": 0.35}]
    sent = []
    for _ in range(6):
        assert "trusted_disturbance" not in hw.true_state() or hw.true_state()["t"] >= 3.0
        hw.step(0.5)
        sent.append(lab.q1[-1])
    assert sent[:3] == [50.0, 50.0, 50.0]
    assert sent[3:] == pytest.approx([32.5, 32.5, 32.5])
    ts = hw.true_state()
    assert ts["trusted_disturbance"] == [{"family": "pump_derate", "at_t": 3.0, "magnitude": 0.35}]


def test_hw_pump_derate_explicit_magnitude_and_reset_clears():
    hw, lab, _ = _hw()
    hw.reset(0)
    hw.schedule_disturbance(DisturbanceSpec(family="pump_derate", at_t=0.0, magnitude=0.5))
    hw.step(0.8)
    assert lab.q1[-1] == pytest.approx(40.0)
    hw.reset(0)
    assert hw.applied_disturbances == []
    assert "trusted_disturbance" not in hw.true_state()
    hw.step(0.8)
    assert lab.q1[-1] == pytest.approx(80.0)
    hw.emergency_stop()
    assert lab.q1[-1] == 0.0 and lab.q2[-1] == 0.0
    with pytest.raises(ValueError):
        hw.schedule_disturbance(DisturbanceSpec(family="pump_derate", at_t=0.0, magnitude=1.5))


@pytest.mark.parametrize("family", ["extra_leak", "drain_shift", "actuator_lag"])
def test_hw_other_families_still_operator_only(family):
    hw, _lab, _ = _hw()
    hw.reset(0)
    with pytest.raises(NotImplementedError, match="operator"):
        hw.schedule_disturbance(DisturbanceSpec(family=family, at_t=10.0))
    assert hw.applied_disturbances == []


# ------------------------------------------------------------------ Part B: board verification
class ConstCtrl:
    """Trusted test double with a `source` attribute (sha256 is taken from it, like the sandbox's)."""

    isolation = "test"

    def __init__(self, u: float, name: str) -> None:
        self.u, self.name = u, name
        self.source = f"# test controller {name} u={u}\n"
        self.closed = False

    def reset(self) -> None:
        pass

    def step(self, obs: dict) -> float:
        return self.u

    def close(self) -> None:
        self.closed = True


def _sha(s: str) -> str:
    return hashlib.sha256(s.encode()).hexdigest()


def _setup(record: list):
    plant = vob.fake_board()
    lab = plant._open()
    orig = plant.emergency_stop

    def estop() -> None:
        orig()
        record.append(("estop", lab.q1[-1] if lab.q1 else 0.0))

    plant.emergency_stop = estop  # type: ignore[method-assign]
    return plant, lab


TWIN = TwinParams(K_c=76.0, tau_s=175.0, L_s=30.0, Ta_c=22.0, noise_std_c=0.05)


def _trials():
    c1, c2 = ConstCtrl(0.40, "v1"), ConstCtrl(0.55, "v2")
    return [("v1", lambda: c1, _sha(c1.source)), ("v2", lambda: c2, _sha(c2.source))], (c1, c2)


def test_board_verification_trusted_derate_on_fake_board():
    record: list = []
    plant, lab = _setup(record)
    trials, (c1, c2) = _trials()

    def on_event(kind, **p):
        record.append((kind, p.get("label"), lab.q1[-1] if lab.q1 else None))

    pre, post = 100.0, 400.0
    bv = run_board_verification(
        plant, trials, supervisor=Supervisor(SafetyLimits.from_profile(TCLAB)), profile=TCLAB, pre_s=pre,
        post_s=post, disturbance=DisturbanceSpec(family="pump_derate", at_t=pre), on_event=on_event,
        twin_factory=twin_factory(TWIN), prediction_basis="original_twin_plus_trusted_derate",
    )
    assert bv.order == ["v1", "v2"] and [t.label for t in bv.trials] == ["v1", "v2"]
    assert bv.disturbance == {"family": "pump_derate", "magnitude": 0.35, "applied_by": "trusted_actuator", "at_t": pre}
    for t, u in zip(bv.trials, (0.40, 0.55), strict=True):
        assert len(t.trace.steps) == int(pre + post) and t.trace.disturbance_at == pre
        assert t.controller_sha256 == _sha(f"# test controller {t.label} u={u}\n")
        assert not t.interlock_hit and t.hard_violations == 0 and t.invalid_outputs == 0
        assert t.post_mae > 0 and 0.0 <= t.post_in_band <= 1.0
    assert c1.closed and c2.closed
    # the Q1 percent actually sent: full before pre_s, derated by 0.35 from pre_s, in both trials
    nonzero = [q for q in lab.q1 if q > 0]
    assert sorted({round(q, 6) for q in nonzero}) == [26.0, 35.75, 40.0, 55.0]
    assert sum(1 for q in nonzero if abs(q - 26.0) < 1e-9) == int(post)
    assert sum(1 for q in nonzero if abs(q - 35.75) < 1e-9) == int(post)
    # heater idled (Q1 = 0) before each trial is reported finished
    for r in record:
        if r[0] == "board_trial_finished":
            assert r[2] == 0.0
    kinds = [r[0] for r in record if r[0] != "estop"]
    assert kinds == ["twin_trial_started", "twin_trial_started", "board_trial_started", "board_trial_finished",
                     "board_trial_started", "board_trial_finished", "board_verification"]
    c = bv.comparison
    assert set(c) == {"post_mae_v1", "post_mae_v2", "reduction", "in_band_v1", "in_band_v2"}
    assert c["reduction"] == pytest.approx(1 - c["post_mae_v2"] / c["post_mae_v1"])
    # protocol-matched twin prediction, computed before the board trials
    tp = bv.twin_prediction
    assert tp is not None and tp["prediction_basis"] == "original_twin_plus_trusted_derate"
    assert [t["label"] for t in tp["trials"]] == ["v1", "v2"] and "start_T_display" not in tp["trials"][0]
    pvb = bv.prediction_vs_board
    assert pvb["post_mae_v1"]["measured"] == c["post_mae_v1"]
    assert pvb["reduction"]["predicted"] == tp["comparison"]["reduction"]
    assert pvb["direction_agrees"] == ((tp["comparison"]["reduction"] > 0) == (c["reduction"] > 0))
    json.dumps(bv.model_dump(mode="json"))  # serializable


def test_board_verification_operator_hooks_and_no_twin():
    record: list = []
    plant, lab = _setup(record)
    trials, _ = _trials()
    calls: list[str] = []

    def pause():
        calls.append(f"go@{plant._t:.0f}")
        # blocking hook

    def between():
        calls.append("off")
        assert lab.q1[-1] == 0.0  # heater idle while the operator works

    def on_event(kind, **p):
        calls.append(kind)

    bv = run_board_verification(
        plant, trials, supervisor=Supervisor(SafetyLimits.from_profile(TCLAB)), profile=TCLAB, pre_s=50.0,
        post_s=50.0, disturbance=None, pause_for_operator=pause, pause_between_trials=between, on_event=on_event,
        twin_missing_reason="twin_fit_after_change.json missing",
    )
    assert calls == ["board_trial_started", "go@50", "board_trial_finished", "off",
                     "board_trial_started", "go@50", "board_trial_finished", "board_verification"]
    assert bv.disturbance["applied_by"] == "operator"
    assert all(t.trace.disturbance_at == 50.0 for t in bv.trials)
    assert bv.twin_prediction is None and bv.twin_prediction_reason == "twin_fit_after_change.json missing"
    assert bv.prediction_vs_board == {}
    assert plant.applied_disturbances == []


def test_board_verification_idles_heater_on_exception():
    record: list = []
    plant, lab = _setup(record)

    class Boom(ConstCtrl):
        def reset(self) -> None:
            raise RuntimeError("boom")

    b = Boom(0.9, "v1")
    with pytest.raises(RuntimeError, match="boom"):
        run_board_verification(plant, [("v1", lambda: b)], supervisor=Supervisor(SafetyLimits.from_profile(TCLAB)),
                               profile=TCLAB, pre_s=10.0, post_s=10.0,
                               disturbance=DisturbanceSpec(family="pump_derate", at_t=10.0))
    assert record and record[-1][0] == "estop" and lab.q1[-1] == 0.0 and b.closed


def test_board_verification_rejects_sha_mismatch():
    plant = vob.fake_board()
    c = ConstCtrl(0.4, "v1")
    with pytest.raises(RuntimeError, match="sha256"):
        run_board_verification(plant, [("v1", lambda: c, "0" * 64)], supervisor=Supervisor(SafetyLimits.from_profile(TCLAB)),
                               profile=TCLAB, pre_s=10.0, post_s=10.0,
                               disturbance=DisturbanceSpec(family="pump_derate", at_t=10.0))


# ------------------------------------------------------------------ Part C: bundle hash check
@pytest.fixture
def hw2_copy(tmp_path: Path) -> Path:
    if not HW2.exists():
        pytest.skip("hw2 bundle not present")
    dst = tmp_path / "runs" / HW2.name
    shutil.copytree(HW2, dst)
    return dst


def test_verify_on_board_aborts_on_tampered_controller(hw2_copy: Path, capsys):
    assert vob.promoted_version(hw2_copy) == 2
    p = hw2_copy / "controller_v2.py"
    p.write_bytes(p.read_bytes().replace(b"0.", b"9.", 1))
    n_events = len((hw2_copy / "event_log.jsonl").read_text().splitlines())
    rc = vob.main(["--run", hw2_copy.name, "--root", str(hw2_copy.parent), "--disturbance", "derate",
                   "--fake-board", "--sandbox", "subprocess_dev_only"])
    assert rc == 3
    assert "does not match meta.json" in capsys.readouterr().err
    assert not (hw2_copy / "board_verification.json").exists()
    assert len((hw2_copy / "event_log.jsonl").read_text().splitlines()) == n_events


# ------------------------------------------------------------------ Part E: audit check
def _synthetic_bv(run_dir: Path, **over) -> dict:
    sha1 = json.loads((run_dir / "controller_v1.meta.json").read_text())["sha256"]
    sha2 = json.loads((run_dir / "controller_v2.meta.json").read_text())["sha256"]

    def trial(label, sha):
        steps = [{"t": float(k), "y": 0.5, "h_true": 0.5, "u_requested": 0.3, "u_applied": 0.3, "override": False,
                  "reason": "ok"} for k in range(20)]
        return {"label": label, "controller_sha256": sha, "start_T_display": 30.0,
                "trace": {"steps": steps, "dt": 1.0, "target": 0.5, "disturbance_at": 10.0, "meta": {}},
                "post_mae": 0.0, "post_in_band": 1.0, "overrides": 0, "hard_violations": 0, "invalid_outputs": 0,
                "interlock_hit": False}

    bv = {"trials": [trial("v1", sha1), trial("v2", sha2)], "order": ["v1", "v2"], "pre_s": 10.0, "post_s": 10.0,
          "disturbance": {"family": "pump_derate", "magnitude": 0.35, "applied_by": "trusted_actuator"},
          "comparison": {}, "fake_board": False}
    bv.update(over)
    return bv


def _check8(run_dir: Path):
    return audit_run.check_board_verification(run_dir)


def test_audit_board_verification_skipped_and_pass(hw2_copy: Path):
    c = _check8(hw2_copy)
    assert c.status == "PASS" and "skipped" in c.details[0]
    (hw2_copy / "board_verification.json").write_text(json.dumps(_synthetic_bv(hw2_copy)))
    c = _check8(hw2_copy)
    assert c.status == "PASS", c.details
    checks = audit_run.audit(hw2_copy)
    assert [x.number for x in checks][-1] == 8 and all(x.status != "FAIL" for x in checks)


@pytest.mark.parametrize("mutate,msg", [
    (lambda b: b["trials"][1].__setitem__("controller_sha256", "f" * 64), "matches no registered"),
    (lambda b: b["trials"][0]["trace"]["steps"][3].__setitem__("u_applied", 1.2), "outside [0, 1]"),
    (lambda b: b["trials"][0].__setitem__("interlock_hit", True), "interlock_hit"),
    (lambda b: b["trials"][0]["trace"].__setitem__("disturbance_at", 100.0), "empty post-change window"),
    (lambda b: b["trials"][1]["trace"]["steps"][0].__setitem__("t", -1.0), "t < 0"),
])
def test_audit_board_verification_fail_cases(hw2_copy: Path, mutate, msg):
    bv = _synthetic_bv(hw2_copy)
    mutate(bv)
    (hw2_copy / "board_verification.json").write_text(json.dumps(bv))
    c = _check8(hw2_copy)
    assert c.status == "FAIL" and any(msg in d for d in c.details), c.details


def test_audit_board_verification_fake_board_warns(hw2_copy: Path):
    (hw2_copy / "board_verification.json").write_text(json.dumps(_synthetic_bv(hw2_copy, fake_board=True)))
    assert _check8(hw2_copy).status == "WARN"


# ------------------------------------------------------------------ Part F: live readout (camera)
def test_live_readout_prints_every_n_seconds_and_never_alters_commands():
    plant = vob.fake_board()
    lab = plant._open()
    lines: list[str] = []
    ro = vob.LiveReadout(plant, every_s=5.0, out=lines.append)
    ro.on_event("board_trial_started", {"label": "v2"})
    plant.reset(seed=0, scenario=0)
    for _ in range(21):
        plant.step(0.4)
    assert len(lines) >= 4  # t = 0, 5, 10, 15, 20 s buckets (reset tick may land on 0)
    assert all(line.startswith("[v2] t=") and "°C" in line and "heater  40 %" in line for line in lines)
    assert lab.q1[-1] == 40.0  # the command sent to the board is untouched
    ro.on_event("operator_disturbance_prompt", {"purpose": "apply"})
    for _ in range(6):
        plant.step(0.4)
    assert "<< change requested" in lines[-1]
