"""ThermalTwin (FOPDT) plant and fit_twin."""
from __future__ import annotations

import numpy as np
import pytest

from backend.plant.tclab_plant import TCLabSim
from backend.plant.thermal_twin import ThermalTwin, TwinParams, fit_twin, simulate_fopdt, twin_factory
from backend.schemas import DisturbanceSpec, Trace, TraceStep

TRUE = TwinParams(K_c=58.0, tau_s=140.0, L_s=25.0, Ta_c=23.0, noise_std_c=0.1)


def _const(plant, u: float, n: int) -> Trace:
    steps = []
    for _ in range(n):
        o = plant.observe()
        h = plant.true_state()["h_true"]
        plant.step(u)
        steps.append(TraceStep(t=o.t, y=o.y, h_true=h, u_requested=u, u_applied=u, override=False, reason="ok"))
    return Trace(steps=steps, dt=1.0, target=0.4167, meta={"kind": "constant_input", "u": u})


def _truth(plant, u: float, n: int) -> np.ndarray:
    h = []
    for _ in range(n):
        h.append(plant.true_state()["h_true"])
        plant.step(u)
    return np.array(h)


def test_twin_step_matches_closed_form_and_simulate():
    tw = ThermalTwin.from_params(TRUE)
    tw.reset(0)
    h = _truth(tw, 1.0, 400)
    x = simulate_fopdt(np.ones(400), TRUE.K_c / 60, TRUE.tau_s, TRUE.L_s, (TRUE.Ta_c - 15.0) / 60, (TRUE.Ta_c - 15.0) / 60)
    assert np.allclose(h, x, atol=1e-12)
    assert np.all(h[:26] == h[0]) and h[27] > h[0]  # 25 s dead time
    t = np.arange(400.0)
    expect = TRUE.Ta_c + TRUE.K_c * (1 - np.exp(-np.clip(t - 25.0, 0, None) / TRUE.tau_s))
    assert np.allclose(h * 60 + 15, expect, atol=0.25)


def test_twin_deterministic_and_api():
    f = twin_factory(TRUE)
    a, b = f(), f()
    assert a is not b and a.dt == 1.0
    a.reset(1, 2)
    b.reset(1, 2)
    ya = [a.step(0.5).y for _ in range(50)]
    yb = [b.step(0.5).y for _ in range(50)]
    assert ya == yb and a.observe().t == 50.0
    assert "0 = 20 °C" in a.public_description()
    with pytest.raises(ValueError):
        a.step(float("nan"))


def test_twin_interlock():
    tw = ThermalTwin(TwinParams(K_c=70.0, tau_s=60.0, L_s=0.0, Ta_c=22.0))
    tw.reset(0)
    for _ in range(600):
        if tw.step(1.0).interlock_high:
            break
    assert tw.true_state()["h_true"] * 60 + 15 >= 69.0


@pytest.mark.parametrize("family", ["pump_derate", "extra_leak", "drain_shift", "actuator_lag"])
def test_twin_disturbances_slow_or_lower_the_response(family):
    base = ThermalTwin(TRUE)
    base.reset(3)
    hb = _truth(base, 0.6, 500)
    d = ThermalTwin(TRUE)
    d.reset(3)
    d.schedule_disturbance(DisturbanceSpec(family=family, at_t=0.0))
    hd = _truth(d, 0.6, 500)
    if family == "actuator_lag":
        assert hd[100] < hb[100] - 0.01 and abs(hd[-1] - hb[-1]) < 0.03
    else:
        assert hd[-1] < hb[-1] - 0.02
    assert d.hidden_params()["disturbances"][0]["applied"]["magnitude"] > 0


def _synthetic_experiments():
    tw = ThermalTwin(TRUE)
    out = []
    for i, (u, n) in enumerate([(0.3, 180), (0.7, 180), (1.0, 150)]):
        tw.reset(0, 50 + i)  # each experiment from a cold start
        out.append(_const(tw, u, n))
    return out


def test_fit_recovers_known_params():
    p = fit_twin(_synthetic_experiments())
    for name in ("K_c", "tau_s", "L_s"):
        assert getattr(p, name) == pytest.approx(getattr(TRUE, name), rel=0.15), (name, p)
    assert abs(p.Ta_c - TRUE.Ta_c) < 0.5
    assert p.report is not None and p.report.rmse < 0.005 and len(p.report.per_trace_rmse) == 3
    # fitted twin's step response vs source
    src, fit = ThermalTwin(TRUE), ThermalTwin(p.model_copy(update={"Ta_c": TRUE.Ta_c}))
    src.reset(9)
    fit.reset(9)
    rmse = float(np.sqrt(np.mean((_truth(src, 0.5, 600) - _truth(fit, 0.5, 600)) ** 2)))
    assert rmse < 0.01, rmse


def test_fit_contiguous_traces_are_one_segment():
    tw = ThermalTwin(TRUE)
    tw.reset(0, 1)
    trs = [_const(tw, 0.5, 150), _const(tw, 0.9, 150), _const(tw, 0.0, 150)]
    p = fit_twin(trs)
    assert p.report.n_segments == 1
    assert p.K_c == pytest.approx(TRUE.K_c, rel=0.15) and p.L_s == pytest.approx(TRUE.L_s, rel=0.15)


def test_fit_short_or_flat_experiments_warn_not_crash():
    tw = ThermalTwin(TRUE)
    tw.reset(0)
    p = fit_twin([_const(tw, 0.0, 30)])
    assert any("no_excitation" in w for w in p.report.warnings)
    tw.reset(0)
    p = fit_twin([_const(tw, 0.8, 40)])
    assert p.report.warnings  # short relative to tau
    with pytest.raises(ValueError):
        fit_twin([])


SIM_VS_TWIN_RMSE_LIMIT = 0.05


def test_twin_fitted_on_tclabsim_matches_sim():
    """Discovery-style experiments on TCLabSim (consecutive, no reset), then a 600 s response at
    u = 0.5 from a cold start in the same room. Measured 2026-11-01: RMSE ~0.0046 normalized
    (~0.28 °C), fitted K ~65 °C, tau ~153 s, L ~13.6 s."""
    sim = TCLabSim()
    sim.reset(0, 0)
    trs = [_const(sim, 0.3, 150), _const(sim, 0.6, 180), _const(sim, 0.0, 120)]
    p = fit_twin(trs)
    sim.reset(0, 0)
    tw = ThermalTwin(p)
    tw.reset(0, 0)
    rmse = float(np.sqrt(np.mean((_truth(sim, 0.5, 600) - _truth(tw, 0.5, 600)) ** 2)))
    print(f"sim-vs-twin rmse={rmse:.4f} params={p.model_dump(exclude={'report'})} fit_rmse={p.report.rmse:.4f}")
    assert rmse < SIM_VS_TWIN_RMSE_LIMIT, rmse
