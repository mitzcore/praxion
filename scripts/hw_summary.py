"""Generate docs/HARDWARE_RESULTS.md from every physical-TCLab bundle under artifacts/runs.

  uv run python scripts/hw_summary.py [--root artifacts/runs] [--glob 'hw*'] [--out docs/HARDWARE_RESULTS.md]
                                      [--png docs/img/hardware_results.png]

Aggregates ONLY what the bundles contain (profile name "tclab" in result.json); a missing file gives "—".
Deterministic: no timestamps of generation, runs sorted by run id, so re-runs are idempotent.
If matplotlib is not installed the figure is written as a hand-built SVG next to the --png path.

Units: every MAE in a bundle is on the normalized y scale; °C = normalized * profile.y_scale (60 for
tclab). Temperatures (y) are °C = y * y_scale + y_offset. board_verification.json post_mae values are
assumed normalized as well, unless the file declares "units": "C".
"""
from __future__ import annotations

import argparse
import json
import math
import re
import statistics
import sys
from datetime import UTC, datetime
from pathlib import Path

DASH = "—"


# ---------------------------------------------------------------- statistics

def sign_test_one_sided(k: int, n: int) -> float:
    """Exact one-sided sign test: P(X >= k) for X ~ Binomial(n, 1/2)."""
    if n <= 0:
        return float("nan")
    return sum(math.comb(n, i) for i in range(k, n + 1)) / 2 ** n


def _binom_cdf(x: int, n: int, p: float) -> float:
    return sum(math.comb(n, i) * p ** i * (1 - p) ** (n - i) for i in range(x + 1))


def _bisect(f, lo: float = 0.0, hi: float = 1.0, iters: int = 200) -> float:
    """Root of a monotone f on [lo, hi]."""
    flo = f(lo)
    for _ in range(iters):
        mid = (lo + hi) / 2
        fm = f(mid)
        if (fm > 0) == (flo > 0):
            lo, flo = mid, fm
        else:
            hi = mid
    return (lo + hi) / 2


def clopper_pearson(x: int, n: int, alpha: float = 0.05) -> tuple[float, float]:
    """Exact two-sided (1 - alpha) Clopper–Pearson interval for a binomial proportion x/n."""
    if n <= 0:
        return float("nan"), float("nan")
    a = alpha / 2
    lower = 0.0 if x == 0 else _bisect(lambda p: (1 - _binom_cdf(x - 1, n, p)) - a)
    upper = 1.0 if x == n else _bisect(lambda p: _binom_cdf(x, n, p) - a)
    return lower, upper


# ---------------------------------------------------------------- bundle reading

def _load_json(p: Path):
    try:
        return json.loads(p.read_text())
    except (OSError, ValueError):
        return None


def _load_jsonl(p: Path) -> list[dict] | None:
    try:
        out = []
        with p.open(encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        out.append(json.loads(line))
                    except ValueError:
                        continue
        return out
    except OSError:
        return None


def _num(x):
    return float(x) if isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(x) else None


def read_bundle(d: Path) -> dict | None:
    """Extract every reported number from one bundle, with the files it came from."""
    result = _load_json(d / "result.json")
    if not isinstance(result, dict) or (result.get("profile") or {}).get("name") != "tclab":
        return None
    sources: list[str] = ["result.json"]
    prof = result["profile"]
    scale = float(prof.get("y_scale") or 1.0)
    offset = float(prof.get("y_offset") or 0.0)
    r: dict = {"run_id": result.get("run_id") or d.name, "dir": str(d), "stage": result.get("stage"),
               "y_scale": scale, "y_offset": offset, "model_id": result.get("model_id"),
               "elapsed_min": (_num(result.get("elapsed_s")) or 0) / 60 if _num(result.get("elapsed_s")) else None}

    events = _load_jsonl(d / "event_log.jsonl") or []
    if events:
        sources.append("event_log.jsonl")
    started = next((e for e in events if e.get("kind") == "run_started"), events[0] if events else None)
    r["date"] = (datetime.fromtimestamp(started["ts"], tz=UTC).strftime("%Y-%m-%d %H:%M UTC")
                 if started and _num(started.get("ts")) else None)

    # the run's OWN disturbance, from the run itself (never from board_verification.json)
    bv = _load_json(d / "board_verification.json")
    op_applied = next((e for e in events if e.get("kind") == "operator_disturbance_applied"), None)
    sched = next((e for e in events if e.get("kind") == "disturbance_scheduled"), None)
    mon_res = result.get("monitoring") or {}
    if op_applied is not None or (sched or {}).get("operator_applied") is True:
        r["run_change"] = ("operator", None)
        r["disturbance"] = "operator (fan)"
    elif mon_res.get("disturbance_family"):
        r["run_change"] = ("trusted", mon_res["disturbance_family"])
        r["disturbance"] = f"{mon_res['disturbance_family']} (trusted)"
    else:
        r["run_change"] = None
        r["disturbance"] = DASH if r["stage"] != "FAILED" else "not reached"

    # G2 on the first candidate
    ev1 = _load_json(d / "evaluation_v1.json")
    if isinstance(ev1, dict):
        sources.append("evaluation_v1.json")
        agg = ev1.get("aggregate") or {}
        r["g2_pass"] = bool(ev1.get("gate_passed"))
        r["g2_n_passed"] = _num(agg.get("n_passed"))
        r["g2_n_episodes"] = _num(agg.get("n_episodes"))
        mm = _num(agg.get("median_mae"))
        r["g2_median_mae_c"] = mm * scale if mm is not None else None
    else:
        r["g2_pass"] = r["g2_n_passed"] = r["g2_n_episodes"] = r["g2_median_mae_c"] = None

    # detection latency
    mon = _load_json(d / "monitoring.json")
    mres = next((e for e in reversed(events) if e.get("kind") == "monitoring_result"), None)
    degraded_at = _num((mres or {}).get("degraded_at_t"))
    if degraded_at is None and isinstance(mon, dict):
        degraded_at = _num(mon.get("degraded_at_t"))
    if isinstance(mon, dict):
        sources.append("monitoring.json")
    dist_t = _num((op_applied or {}).get("t"))
    if dist_t is None and isinstance(mon, dict):
        dist_t = _num((mon.get("trace") or {}).get("disturbance_at"))
    if dist_t is None:
        dist_t = _num(mon_res.get("disturbance_at_t"))
    r["detected"] = bool((mres or {}).get("degraded")) if mres else (bool(mon.get("degraded_at_t") is not None)
                                                                     if isinstance(mon, dict) else None)
    r["detection_latency_s"] = degraded_at - dist_t if degraded_at is not None and dist_t is not None else None
    r["disturbance_t"] = dist_t
    r["reached_monitoring"] = mres is not None or isinstance(mon, dict)

    # v1 on-board drift minimum after the disturbance (°C)
    r["v1_min_after_c"] = None
    if isinstance(mon, dict) and dist_t is not None:
        ys = [_num(s.get("y")) for s in ((mon.get("trace") or {}).get("steps") or [])
              if _num(s.get("t")) is not None and s["t"] >= dist_t]
        ys = [y for y in ys if y is not None]
        if ys:
            r["v1_min_after_c"] = min(ys) * scale + offset

    # adaptation (latest)
    adapt_ev = next((e for e in reversed(events) if e.get("kind") == "adaptation_result"), None)
    vers = sorted(int(m.group(1)) for p in d.glob("adaptation_v*.json") if (m := re.match(r"adaptation_v(\d+)\.json$", p.name)))
    adapt_v = vers[-1] if vers else None
    adapt = _load_json(d / f"adaptation_v{adapt_v}.json") if adapt_v else None
    if isinstance(adapt, dict):
        sources.append(f"adaptation_v{adapt_v}.json")
    r["diagnosis_correct"] = (adapt.get("diagnosis_correct") if isinstance(adapt, dict)
                              else (adapt_ev or {}).get("diagnosis_correct"))
    r["diagnosis_category"] = adapt.get("diagnosis_category") if isinstance(adapt, dict) else None
    r["adapted"] = isinstance(adapt, dict) or adapt_ev is not None
    r["v2_nominal_g2"] = (adapt.get("nominal_gate") if isinstance(adapt, dict)
                          else (adapt_ev or {}).get("nominal_gate_passed"))

    # twin-predicted post-change MAE
    r["twin_v1_c"] = r["twin_v2_c"] = r["twin_reduction"] = None
    edv1 = _load_json(d / "evaluation_disturbance_v1.json")
    edv2 = _load_json(d / f"evaluation_disturbance_v{adapt_v}.json") if adapt_v else None
    if isinstance(edv1, dict):
        sources.append("evaluation_disturbance_v1.json")
        v = _num((edv1.get("aggregate") or {}).get("median_post_disturbance_mae"))
        r["twin_v1_c"] = v * scale if v is not None else None
    if isinstance(edv2, dict):
        sources.append(f"evaluation_disturbance_v{adapt_v}.json")
        v = _num((edv2.get("aggregate") or {}).get("median_post_disturbance_mae"))
        r["twin_v2_c"] = v * scale if v is not None else None
    red = _num(((adapt or {}).get("comparison") or {}).get("median_reduction")) if isinstance(adapt, dict) else None
    if red is None and r["twin_v1_c"] and r["twin_v2_c"] is not None:
        red = 1 - r["twin_v2_c"] / r["twin_v1_c"]
    r["twin_reduction"] = red

    # repair promoted: final transition to COMPLETE naming a version >= 2 candidate
    hist = result.get("stage_history") or []
    last = hist[-1] if hist else {}
    cand_id = last.get("candidate_id") or ""
    mv = re.search(r"-v(\d+)$", cand_id)
    r["repair_promoted"] = bool(last.get("to") == "COMPLETE" and mv and int(mv.group(1)) >= 2)

    # twin fits
    for name, key in (("twin_fit.json", "twin_fit"), ("twin_fit_after_change.json", "twin_fit_after")):
        tf = _load_json(d / name)
        if isinstance(tf, dict):
            sources.append(name)
            r[key] = {"K_c": _num(tf.get("K_c")), "tau_s": _num(tf.get("tau_s")), "L_s": _num(tf.get("L_s")),
                      "Ta_c": _num(tf.get("Ta_c")), "rmse_c": (_num((tf.get("report") or {}).get("rmse")) or 0) * scale
                      if _num((tf.get("report") or {}).get("rmse")) is not None else None}
        else:
            r[key] = None

    # model calls
    calls = _load_jsonl(d / "model_calls.jsonl")
    if calls is not None:
        sources.append("model_calls.jsonl")
        r["n_calls"] = len(calls)
        r["n_failed_calls"] = sum(1 for c in calls if c.get("ok") is False)
        r["cost_usd"] = sum(_num(c.get("cost_usd")) or 0.0 for c in calls)
    else:
        r["n_calls"] = r["n_failed_calls"] = r["cost_usd"] = None

    # board verification
    r["board"] = None
    if isinstance(bv, dict):
        sources.append("board_verification.json")
        cmp_ = bv.get("comparison") or {}
        f = 1.0 if str(bv.get("units", cmp_.get("units", ""))).replace("°", "").upper() in {"C", "DEGC"} else scale
        b1, b2 = _num(cmp_.get("post_mae_v1")), _num(cmp_.get("post_mae_v2"))
        bred = _num(cmp_.get("reduction"))
        if bred is None and b1 and b2 is not None:
            bred = 1 - b2 / b1
        r["board"] = {"fake_board": bool(bv.get("fake_board")), "v1_c": b1 * f if b1 is not None else None, "v2_c": b2 * f if b2 is not None else None,
                      "reduction": bred, "in_band_v1": _num(cmp_.get("in_band_v1")),
                      "in_band_v2": _num(cmp_.get("in_band_v2")), "order": bv.get("order"),
                      "trials": [{k: t.get(k) for k in ("label", "controller_sha256", "start_T_display", "post_mae",
                                                         "post_in_band", "overrides", "hard_violations",
                                                         "invalid_outputs", "interlock_hit")}
                                 for t in (bv.get("trials") or []) if isinstance(t, dict)]}
        bd = bv.get("disturbance") if isinstance(bv.get("disturbance"), dict) else {}
        r["board"]["change"] = board_change_label(bd)
        r["board"]["mismatch"] = not change_matches(r["run_change"], bd)
    r["sources"] = sources
    return r


def board_change_label(bd: dict) -> str:
    fam, by = bd.get("family"), bd.get("applied_by")
    return "/".join(str(x) for x in (fam, by) if x) or "unknown"


def change_matches(run_change: tuple[str, str | None] | None, bd: dict) -> bool:
    """Was the board verification done under the same kind of change the run itself experienced?
    operator run <-> applied_by operator; trusted run with family F <-> applied_by trusted* and family F.
    A run whose own change is unknown matches nothing."""
    if run_change is None:
        return False
    by = str(bd.get("applied_by") or "")
    if run_change[0] == "operator":
        return by == "operator"
    return by.startswith("trusted") and bd.get("family") == run_change[1]


# ---------------------------------------------------------------- formatting

def _f(x, fmt="{:.2f}"):
    return DASH if x is None else fmt.format(x)


def _yn(x):
    return DASH if x is None else ("yes" if x else "no")


def _pct(x):
    return DASH if x is None else f"{x * 100:.0f}%"


def _sign(x):
    return 0 if x is None or x == 0 else (1 if x > 0 else -1)


def aggregate(runs: list[dict]) -> dict:
    verified = [r for r in runs if r["board"] and not r["board"]["fake_board"]
                and not r["board"]["mismatch"] and r["board"]["v1_c"] is not None and r["board"]["v2_c"] is not None]
    success = [r for r in verified if (r["board"]["reduction"] or 0) > 0 and r["board"]["in_band_v1"] is not None
               and r["board"]["in_band_v2"] is not None and r["board"]["in_band_v2"] > r["board"]["in_band_v1"]]
    lower = [r for r in verified if r["board"]["v2_c"] < r["board"]["v1_c"]]
    ties = [r for r in verified if r["board"]["v2_c"] == r["board"]["v1_c"]]
    n_sign = len(verified) - len(ties)
    twin_red = [r["twin_reduction"] for r in runs if r["twin_reduction"] is not None]
    board_red = [r["board"]["reduction"] for r in verified if r["board"]["reduction"] is not None]
    return {
        "attempted": len(runs), "completed": sum(1 for r in runs if r["stage"] == "COMPLETE"),
        "g2_first": sum(1 for r in runs if r["g2_pass"]), "detected": sum(1 for r in runs if r["detected"]),
        "diag_correct": sum(1 for r in runs if r["diagnosis_correct"] is True),
        "promoted": sum(1 for r in runs if r["repair_promoted"]),
        "n_monitored": sum(1 for r in runs if r["reached_monitoring"]),
        "n_adapted": sum(1 for r in runs if r["adapted"]),
        "n_verified": len(verified), "n_success": len(success),
        "median_twin_reduction": statistics.median(twin_red) if twin_red else None,
        "median_board_reduction": statistics.median(board_red) if board_red else None,
        "n_twin": len(twin_red), "n_board": len(board_red),
        "sign_k": len(lower), "sign_n": n_sign, "n_ties": len(ties),
        "sign_p": sign_test_one_sided(len(lower), n_sign) if n_sign > 0 else None,
        "cp": clopper_pearson(len(success), len(verified)) if verified else None,
        "verified": verified,
    }


def render_markdown(runs: list[dict], agg: dict, fig_rel: str | None, root_display: str, glob: str) -> str:
    L: list[str] = []
    L.append("# Hardware results (physical TCLab board)")
    L.append("")
    L.append(f"Generated by `uv run python scripts/hw_summary.py` from every bundle under `{root_display}/{glob}` whose "
             "`result.json` has profile `tclab`. Every number below is read from a bundle file listed in "
             "[Sources](#sources); nothing is typed by hand. Absent data is shown as —. MAE values are the bundle's "
             "normalized MAE × `profile.y_scale` (60 °C); temperatures are y × 60 + 15 °C.")
    L.append("")
    L.append("**Twin-predicted** numbers are scored by the independent evaluator on the thermal twin fitted from the "
             "board's own traces (hidden seeds). **Board-measured** numbers come from `board_verification.json`, "
             "i.e. v1 and v2 each run on the physical heater after the change (order counterbalanced).")
    L.append("")
    L.append("## Summary")
    L.append("")
    a = agg
    L.append("| measure | value |")
    L.append("|---|---|")
    L.append(f"| runs attempted | {a['attempted']} |")
    L.append(f"| runs COMPLETE | {a['completed']} |")
    L.append(f"| first candidate passed G2 (twin, hidden seeds) | {a['g2_first']} / {a['attempted']} |")
    L.append(f"| change detected by the trusted monitor | {a['detected']} / {a['n_monitored']} runs that reached monitoring |")
    L.append(f"| diagnosis correct | {a['diag_correct']} / {a['n_adapted']} runs that reached adaptation |")
    L.append(f"| repair (v ≥ 2) promoted | {a['promoted']} / {a['n_adapted']} runs that reached adaptation |")
    L.append("| board-verified improvement (board reduction > 0 and in-band v2 > v1) | "
             + (f"{a['n_success']} / {a['n_verified']}" if a["n_verified"] else "not yet measured (0 runs with a matching, real-board board_verification.json)")
             + " |")
    L.append(f"| median twin-predicted post-change MAE reduction | {_pct(a['median_twin_reduction'])}"
             + (f" (n={a['n_twin']})" if a["n_twin"] else "") + " |")
    L.append("| median board-measured post-change MAE reduction | "
             + (f"{_pct(a['median_board_reduction'])} (n={a['n_board']})" if a["n_board"] else "not yet measured") + " |")
    L.append("")
    L.append("## Per run")
    L.append("")
    L.append("| run id | date | disturbance | final stage | G2 v1 (n/10, median MAE °C) | detection latency s | "
             "diagnosis correct | twin post-change MAE v1 → v2 °C (reduction) | board post-change MAE v1 → v2 °C "
             "(reduction) | v1 on-board min after change °C | cost USD | wall min |")
    L.append("|---|---|---|---|---|---|---|---|---|---|---|---|")
    for r in runs:
        g2 = DASH if r["g2_pass"] is None else (
            f"{_yn(r['g2_pass'])} ({_f(r['g2_n_passed'], '{:.0f}')}/{_f(r['g2_n_episodes'], '{:.0f}')}, "
            f"{_f(r['g2_median_mae_c'])})")
        twin = (DASH if r["twin_v1_c"] is None and r["twin_v2_c"] is None else
                f"{_f(r['twin_v1_c'])} → {_f(r['twin_v2_c'])} ({_pct(r['twin_reduction'])})")
        b = r["board"]
        board = DASH if not b else (("fake board, excluded: " if b["fake_board"] else "")
                                    + f"{_f(b['v1_c'])} → {_f(b['v2_c'])} ({_pct(b['reduction'])})"
                                    + (f" mismatch (different change: {b['change']}), excluded" if b["mismatch"] else ""))
        L.append(f"| `{r['run_id']}` | {r['date'] or DASH} | {r['disturbance']} | {r['stage']} | {g2} | "
                 f"{_f(r['detection_latency_s'], '{:.0f}')} | {_yn(r['diagnosis_correct'])} | {twin} | {board} | "
                 f"{_f(r['v1_min_after_c'], '{:.1f}')} | {_f(r['cost_usd'], '{:.3f}')} | {_f(r['elapsed_min'], '{:.0f}')} |")
    L.append("")
    L.append("Detection latency = `monitoring_result.degraded_at_t` − disturbance time (`operator_disturbance_applied.t`, "
             "else `monitoring.json` `trace.disturbance_at`). Twin post-change MAE = `aggregate.median_post_disturbance_mae` "
             "of `evaluation_disturbance_v1.json` and of the repaired version; reduction = `adaptation_v*.json` "
             "`comparison.median_reduction` (median of per-seed reductions). Board columns = `board_verification.json` "
             "`comparison`; a board file recorded under a different change than the run's own (operator ↔ operator, "
             "trusted family F ↔ trusted_actuator family F) is shown as \"mismatch\" and excluded from every board "
             "statistic. The disturbance column is the run's own change (events / `result.json`), never the board "
             "file's. The v1 minimum is the lowest y in `monitoring.json` at or after the disturbance time.")
    L.append("")
    L.append("Notes per run (from the same files):")
    L.append("")
    for r in runs:
        bits = []
        if r["repair_promoted"]:
            bits.append("repair promoted")
        if r["v2_nominal_g2"] is not None:
            bits.append(f"repaired controller nominal G2: {'pass' if r['v2_nominal_g2'] else 'fail'}")
        if r["diagnosis_category"]:
            bits.append(f"diagnosis category `{r['diagnosis_category']}`")
        if r["n_calls"] is not None:
            bits.append(f"{r['n_calls']} model calls ({r['n_failed_calls']} failed), model `{r['model_id']}`")
        tf = r.get("twin_fit")
        if tf:
            bits.append(f"twin fit K={_f(tf['K_c'], '{:.1f}')} °C, τ={_f(tf['tau_s'], '{:.0f}')} s, "
                        f"L={_f(tf['L_s'], '{:.0f}')} s, Ta={_f(tf['Ta_c'], '{:.1f}')} °C, rmse={_f(tf['rmse_c'])} °C")
        ta = r.get("twin_fit_after")
        if ta:
            bits.append(f"after-change fit K={_f(ta['K_c'], '{:.1f}')} °C, τ={_f(ta['tau_s'], '{:.0f}')} s, "
                        f"L={_f(ta['L_s'], '{:.0f}')} s, rmse={_f(ta['rmse_c'])} °C")
        L.append(f"- `{r['run_id']}`: " + "; ".join(bits) + ".")
    L.append("")
    L.append("## Twin prediction vs board measurement")
    L.append("")
    if not a["verified"]:
        L.append("Not yet measured: no bundle contains a matching, real-board `board_verification.json`.")
    else:
        L.append("| run id | order | twin v1 °C | board v1 °C | twin v2 °C | board v2 °C | in-band v1 → v2 (board) | "
                 "twin predicted the board's direction? |")
        L.append("|---|---|---|---|---|---|---|---|")
        for r in a["verified"]:
            b = r["board"]
            tw = _sign((r["twin_v1_c"] - r["twin_v2_c"]) if r["twin_v1_c"] is not None and r["twin_v2_c"] is not None else None)
            bd = _sign(b["v1_c"] - b["v2_c"])
            agree = DASH if tw == 0 or r["twin_v1_c"] is None else ("yes" if tw == bd else "no")
            order = ",".join(b["order"]) if isinstance(b["order"], list) else (b["order"] or DASH)
            L.append(f"| `{r['run_id']}` | {order} | {_f(r['twin_v1_c'])} | {_f(b['v1_c'])} | {_f(r['twin_v2_c'])} | "
                     f"{_f(b['v2_c'])} | {_pct(b['in_band_v1'])} → {_pct(b['in_band_v2'])} | {agree} |")
    L.append("")
    L.append("## Statistics")
    L.append("")
    if a["sign_p"] is None:
        L.append("- Exact one-sided sign test for \"v2 has lower post-change MAE than v1 on the board\": "
                 "not yet measured (0 board-verified runs).")
        L.append("- 95% Clopper–Pearson interval for the board-verified success fraction: not yet measured.")
    else:
        L.append(f"- Exact one-sided sign test for \"v2 has lower post-change MAE than v1 on the board\": "
                 f"{a['sign_k']} of {a['sign_n']} runs (ties excluded: {a['n_ties']}), "
                 f"p = P(X ≥ {a['sign_k']} | n={a['sign_n']}, ½) = {a['sign_p']:.4f}.")
        lo, hi = a["cp"]
        L.append(f"- Board-verified success fraction {a['n_success']}/{a['n_verified']}; "
                 f"95% Clopper–Pearson interval [{lo:.3f}, {hi:.3f}].")
    L.append("- With n this small the interval is wide by construction; the honest reading is the interval, not the "
             "point estimate.")
    L.append("")
    if fig_rel:
        L.append("## Figure")
        L.append("")
        L.append(f"![post-change MAE, twin vs board]({fig_rel})")
        L.append("")
        L.append("Left: per-run post-change MAE (°C), v1 vs v2; hollow = twin-predicted, filled = board-measured. "
                 "Right: twin-predicted vs board-measured MAE with the identity line (empty until a run has "
                 "`board_verification.json`).")
        L.append("")
    L.append("## Sources")
    L.append("")
    for r in runs:
        L.append(f"- `{r['dir']}`: " + ", ".join(f"`{s}`" for s in r["sources"]))
    L.append("")
    return "\n".join(L)


# ---------------------------------------------------------------- figure

def _write_png(runs: list[dict], path: Path) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(11, 4.2))
    for i, r in enumerate(runs):
        if r["twin_v1_c"] is not None:
            ax1.plot([i - 0.1], [r["twin_v1_c"]], "o", mfc="none", mec="C0")
        if r["twin_v2_c"] is not None:
            ax1.plot([i + 0.1], [r["twin_v2_c"]], "s", mfc="none", mec="C1")
        if r["board"]:
            if r["board"]["v1_c"] is not None:
                ax1.plot([i - 0.1], [r["board"]["v1_c"]], "o", color="C0")
            if r["board"]["v2_c"] is not None:
                ax1.plot([i + 0.1], [r["board"]["v2_c"]], "s", color="C1")
            for v, m, c in (("v1", "o", "C0"), ("v2", "s", "C1")):
                tw, bd = r[f"twin_{v}_c"], r["board"][f"{v}_c"]
                if tw is not None and bd is not None:
                    ax2.plot([tw], [bd], m, color=c)
    ax1.set_xticks(range(len(runs)), [r["run_id"].split("-")[0] for r in runs])
    ax1.set_ylabel("post-change MAE (°C)")
    ax1.set_title("v1 (circle) vs v2 (square); hollow=twin, filled=board")
    lim = max([1.0] + [v for r in runs for v in (r["twin_v1_c"], r["twin_v2_c"]) if v is not None]
              + [v for r in runs if r["board"] for v in (r["board"]["v1_c"], r["board"]["v2_c"]) if v is not None]) * 1.1
    ax2.plot([0, lim], [0, lim], "k--", lw=0.8)
    ax2.set_xlim(0, lim)
    ax2.set_ylim(0, lim)
    ax2.set_xlabel("twin-predicted MAE (°C)")
    ax2.set_ylabel("board-measured MAE (°C)")
    ax2.set_title("predicted vs measured")
    fig.tight_layout()
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=120, metadata={"Software": None})
    plt.close(fig)


def _write_svg(runs: list[dict], path: Path) -> None:
    W, H, pad = 900, 360, 50
    pw = (W - 3 * pad) / 2
    ph = H - 2 * pad
    vals = [v for r in runs for v in (r["twin_v1_c"], r["twin_v2_c"]) if v is not None]
    vals += [v for r in runs if r["board"] for v in (r["board"]["v1_c"], r["board"]["v2_c"]) if v is not None]
    vmax = (max(vals) if vals else 1.0) * 1.1 or 1.0
    c1, c2 = "#2f6db5", "#d9822b"
    out = [(f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" '
           'font-family="sans-serif" font-size="11">'), f'<rect width="{W}" height="{H}" fill="#ffffff"/>']

    def frame(x0: float, title: str, xl: str, yl: str) -> None:
        out.append(f'<rect x="{x0:.1f}" y="{pad}" width="{pw:.1f}" height="{ph}" fill="none" stroke="#444"/>')
        out.append(f'<text x="{x0 + pw / 2:.1f}" y="{pad - 12}" text-anchor="middle" font-size="12">{title}</text>')
        out.append(f'<text x="{x0 + pw / 2:.1f}" y="{H - 12}" text-anchor="middle">{xl}</text>')
        out.append(f'<text x="{x0 - 34:.1f}" y="{pad + ph / 2:.1f}" text-anchor="middle" '
                   f'transform="rotate(-90 {x0 - 34:.1f} {pad + ph / 2:.1f})">{yl}</text>')
        for i in range(5):
            v = vmax * i / 4
            y = pad + ph - ph * i / 4
            out.append(f'<text x="{x0 - 4:.1f}" y="{y + 4:.1f}" text-anchor="end">{v:.1f}</text>')

    def mark(x: float, y: float, shape: str, color: str, filled: bool) -> None:
        fill = color if filled else "none"
        if shape == "o":
            out.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="5" fill="{fill}" stroke="{color}" stroke-width="1.6"/>')
        else:
            out.append(f'<rect x="{x - 5:.1f}" y="{y - 5:.1f}" width="10" height="10" fill="{fill}" '
                       f'stroke="{color}" stroke-width="1.6"/>')

    x0 = pad
    frame(x0, "post-change MAE: v1 (circle) vs v2 (square); hollow=twin, filled=board", "run", "MAE (°C)")
    n = max(len(runs), 1)

    def yv(v: float) -> float:
        return pad + ph - ph * v / vmax

    for i, r in enumerate(runs):
        xc = x0 + pw * (i + 0.5) / n
        out.append(f'<text x="{xc:.1f}" y="{pad + ph + 14}" text-anchor="middle">{r["run_id"].split("-")[0]}</text>')
        for v, dx, shape, col in (("v1", -8, "o", c1), ("v2", 8, "s", c2)):
            tw = r[f"twin_{v}_c"]
            if tw is not None:
                mark(xc + dx, yv(tw), shape, col, False)
            if r["board"] and r["board"][f"{v}_c"] is not None:
                mark(xc + dx, yv(r["board"][f"{v}_c"]), shape, col, True)
    x1 = 2 * pad + pw
    frame(x1, "twin-predicted vs board-measured", "twin-predicted MAE (°C)", "board-measured MAE (°C)")
    out.append(f'<line x1="{x1:.1f}" y1="{pad + ph}" x2="{x1 + pw:.1f}" y2="{pad}" stroke="#888" stroke-dasharray="4 3"/>')
    any_pt = False
    for r in runs:
        if not r["board"]:
            continue
        for v, shape, col in (("v1", "o", c1), ("v2", "s", c2)):
            tw, bd = r[f"twin_{v}_c"], r["board"][f"{v}_c"]
            if tw is not None and bd is not None:
                any_pt = True
                mark(x1 + pw * tw / vmax, yv(bd), shape, col, True)
    if not any_pt:
        out.append(f'<text x="{x1 + pw / 2:.1f}" y="{pad + ph / 2:.1f}" text-anchor="middle" fill="#666">'
                   'not yet measured (no board_verification.json)</text>')
    out.append("</svg>")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(out) + "\n")


def write_figure(runs: list[dict], png: Path) -> Path:
    try:
        import matplotlib  # noqa: F401
    except ImportError:
        svg = png.with_suffix(".svg")
        _write_svg(runs, svg)
        return svg
    _write_png(runs, png)
    return png


# ---------------------------------------------------------------- main

def collect(root: Path, glob: str) -> list[dict]:
    runs = []
    for d in sorted(p for p in root.glob(glob) if p.is_dir()):
        r = read_bundle(d)
        if r is not None:
            runs.append(r)
    return runs


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--root", default="artifacts/runs")
    ap.add_argument("--glob", default="hw*")
    ap.add_argument("--out", default="docs/HARDWARE_RESULTS.md")
    ap.add_argument("--png", default="docs/img/hardware_results.png",
                    help="figure path; written as .svg alongside when matplotlib is unavailable")
    ap.add_argument("--no-figure", action="store_true")
    args = ap.parse_args(argv)
    root, out = Path(args.root), Path(args.out)
    runs = collect(root, args.glob)
    agg = aggregate(runs)
    fig_rel = None
    if not args.no_figure:
        fig = write_figure(runs, Path(args.png))
        try:
            fig_rel = str(fig.resolve().relative_to(out.resolve().parent))
        except ValueError:
            fig_rel = str(fig)
    for r in runs:  # display paths relative to cwd when possible, for idempotent output across machines
        try:
            r["dir"] = str(Path(r["dir"]).resolve().relative_to(Path.cwd().resolve()))
        except ValueError:
            pass
    md = render_markdown(runs, agg, fig_rel, args.root, args.glob)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(md)
    print(f"{len(runs)} tclab bundle(s) -> {out}" + (f", figure {fig_rel}" if fig_rel else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
