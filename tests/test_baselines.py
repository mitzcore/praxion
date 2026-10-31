from __future__ import annotations

import math

import numpy as np
import pytest

from backend.controller.protocol import Controller
from backend.controller.runtime import run_episode
from backend.evaluation.baselines import SLOW_PID_TUNING, ConstantController, OnOffController, PIDController
from backend.evaluation.config import (
    BAND,
    DISTURBANCE_AT_S,
    DISTURBANCE_EPISODE_S,
    DISTURBANCE_FAMILIES,
    DISTURBANCE_SEEDS,
    EPISODE_S,
    EXPLORATION_SEEDS,
    GATE2_MIN_INBAND,
    GATE2_MIN_PASS,
    SETTLE_S,
    TARGET,
)
from backend.evaluation.metrics import compute_metrics
from backend.plant.tank_sim import TankSimulator
from backend.safety.supervisor import Supervisor
from backend.schemas import DisturbanceSpec, Trace

SEEDS = EXPLORATION_SEEDS[:10]
BENCH_PLANTS = EXPLORATION_SEEDS[:5]  # plant (machine) seeds
POST_FROM = DISTURBANCE_AT_S + SETTLE_S  # frozen post-disturbance scoring window start


def _metrics(ctrl_factory, seed):
    tr = run_episode(TankSimulator(), ctrl_factory(), Supervisor(), EPISODE_S, TARGET, seed)
    return compute_metrics(tr, SETTLE_S)


def _window(tr: Trace, t0: float) -> dict:
    t, h = tr.times(), tr.h_true()
    hw = h[t >= t0 - 1e-9]
    e = hw - TARGET
    inb = (hw >= BAND[0]) & (hw <= BAND[1])
    return {
        "mae": float(np.mean(np.abs(e))),
        "inb": float(np.mean(inb)),
        "max_err": float(np.max(np.abs(e))),
        "crossings": int(np.sum(np.diff(inb.astype(int)) != 0)),
        "viol": int(np.sum(h >= 0.90)),
    }


def _disturbed(ctrl_factory, plant, scenario, family):
    d = DisturbanceSpec(family=family, at_t=DISTURBANCE_AT_S) if family else None
    return run_episode(TankSimulator(), ctrl_factory(), Supervisor(), DISTURBANCE_EPISODE_S, TARGET, plant,
                       scenario=scenario, disturbance=d)


def _slow_pid():
    return PIDController(**SLOW_PID_TUNING, name="slow_pid")


def test_protocol_conformance():
    for c in (PIDController(), OnOffController(), ConstantController(0.1)):
        assert isinstance(c, Controller)
        assert c.isolation == "trusted"


def test_pid_holds_band_on_exploration_seeds():
    ms = [_metrics(PIDController, s) for s in SEEDS]
    passed = sum(m.in_band_fraction >= GATE2_MIN_INBAND for m in ms)
    assert passed >= GATE2_MIN_PASS, [round(m.in_band_fraction, 3) for m in ms]
    assert all(m.hard_violations == 0 for m in ms)
    assert all(m.override_count == 0 and m.invalid_outputs == 0 for m in ms)


def test_onoff_holds_roughly_around_band():
    ms = [_metrics(OnOffController, s) for s in SEEDS]
    assert all(m.hard_violations == 0 for m in ms)
    assert all(m.mae < 0.05 for m in ms), [round(m.mae, 4) for m in ms]
    assert sum(m.in_band_fraction >= 0.5 for m in ms) >= 8


def test_disturbance_families_config():
    assert set(DISTURBANCE_FAMILIES) == {"pump_derate", "extra_leak", "drain_shift", "actuator_lag"}
    assert DISTURBANCE_FAMILIES["actuator_lag"] == "dynamics"


@pytest.mark.parametrize("plant", BENCH_PLANTS)
def test_actuator_lag_degrades_default_pid(plant):
    """Frozen benchmark property (a): on each machine, default PID degrades under actuator_lag on
    >= 4 of the 5 hidden disturbance scenarios."""
    degraded = []
    for scen in DISTURBANCE_SEEDS:
        nom = _window(_disturbed(PIDController, plant, scen, None), DISTURBANCE_AT_S)
        post = _window(_disturbed(PIDController, plant, scen, "actuator_lag"), POST_FROM)
        worse = post["mae"] >= 3.0 * nom["mae"] or post["inb"] < 0.5
        visible = post["crossings"] >= 2 or post["max_err"] > 0.10
        degraded.append(worse and visible)
    assert sum(degraded) >= 4, degraded


@pytest.mark.parametrize("plant", BENCH_PLANTS)
def test_actuator_lag_is_repairable_by_detuned_pi(plant):
    """Frozen benchmark property (b): existence proof that a repair exists on each machine."""
    ok = []
    for scen in DISTURBANCE_SEEDS:
        post = _window(_disturbed(_slow_pid, plant, scen, "actuator_lag"), POST_FROM)
        ok.append(post["inb"] >= 0.70 and post["viol"] == 0)
    assert sum(ok) >= 4, ok


@pytest.mark.parametrize("plant", BENCH_PLANTS)
def test_offset_families_rejected_by_default_pid(plant):
    """Offset families should be absorbed by integral feedback (the monitor should not fire)."""
    for fam, kind in DISTURBANCE_FAMILIES.items():
        if kind != "offset":
            continue
        for scen in DISTURBANCE_SEEDS:
            post = _window(_disturbed(PIDController, plant, scen, fam), POST_FROM)
            assert post["inb"] >= 0.9 and post["viol"] == 0, (fam, plant, scen, post)


def test_print_benchmark_table():
    """Run with `-s` to print per-seed PID rows for docs/BENCHMARKS.md."""
    rows = []
    for ctrl_name, factory in (("baseline_pid", PIDController), ("slow_pid", _slow_pid)):
        for plant in BENCH_PLANTS:
            for scen in DISTURBANCE_SEEDS:
                nom = _window(_disturbed(factory, plant, scen, None), DISTURBANCE_AT_S)
                rows.append((ctrl_name, plant, scen, "nominal", nom))
                for fam in DISTURBANCE_FAMILIES:
                    post = _window(_disturbed(factory, plant, scen, fam), POST_FROM)
                    rows.append((ctrl_name, plant, scen, fam, post))
    print("\n| controller | plant | scenario | family | MAE | in-band | max err | crossings | hard viol |")
    print("|---|---|---|---|---|---|---|---|---|")
    for name, plant, scen, fam, r in rows:
        print(f"| {name} | {plant} | {scen} | {fam} | {r['mae']:.4f} | {r['inb']:.2f} | {r['max_err']:.3f} | "
              f"{r['crossings']} | {r['viol']} |")
    print(f"(nominal scored t >= {DISTURBANCE_AT_S:.0f} s; disturbed scored t >= {POST_FROM:.0f} s; "
          f"episode {DISTURBANCE_EPISODE_S:.0f} s, disturbance at {DISTURBANCE_AT_S:.0f} s)")
    assert rows


def test_pid_output_bounded_and_nan_safe():
    pid = PIDController()
    for y in (0.0, 1.0, 0.6, math.nan):
        u = pid.step({"y": y, "target": 0.6, "dt": 0.1, "elapsed_s": 0.0})
        assert 0.0 <= u <= 1.0


def test_pid_antiwindup_limits_integral():
    pid = PIDController()
    for _ in range(10_000):
        pid.step({"y": 0.0, "target": 0.6, "dt": 0.1, "elapsed_s": 0.0})
    assert pid.ki * pid._i <= 1.0 + 1e-12
    u = [pid.step({"y": 0.7, "target": 0.6, "dt": 0.1, "elapsed_s": 0.0}) for _ in range(5)]
    assert u[-1] < 0.9


def test_pid_reset_clears_state():
    pid = PIDController()
    for _ in range(100):
        pid.step({"y": 0.2, "target": 0.6, "dt": 0.1, "elapsed_s": 0.0})
    pid.reset()
    assert pid._i == 0.0 and pid._y_prev is None


@pytest.mark.parametrize("y,expected", [(0.5, 1.0), (0.61, 1.0), (0.63, 0.0), (0.59, 0.0), (0.57, 1.0)])
def test_onoff_hysteresis(y, expected):
    c = OnOffController(hysteresis=0.02)
    seq = [0.5, 0.61, 0.63, 0.59, 0.57]
    out = None
    for yy in seq[: seq.index(y) + 1]:
        out = c.step({"y": yy, "target": 0.6, "dt": 0.1, "elapsed_s": 0.0})
    assert out == expected
