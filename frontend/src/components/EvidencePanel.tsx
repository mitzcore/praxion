import { useEffect, useMemo, useState } from "react";
import {
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ReferenceArea,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { CHANGED_MACHINE_SUITE, isCelsius, suiteLabel, toDisplay, TANK_DISPLAY, type BoardVerification, type DisplayProfile, type EvalFile, type Evaluations, type Json, type RepairVerdict, type RunDetail, type RunEvent } from "../api";
import { downsample, fmtNum, fmtPct } from "../format";
import BoardVerificationPanel from "./BoardVerificationPanel";

const SERIES_COLORS = ["var(--s1)", "var(--s2)", "var(--s3)", "var(--s4)"];

interface Row {
  key: string;
  who: string;
  baseline: boolean;
  suite: string;
  gate: string;
  gatePassed: boolean | null;
  agg: Json;
}

function rowsFor(files: EvalFile[]): Row[] {
  const out: Row[] = [];
  const baselineDone = new Set<string>();
  for (const f of files) {
    const d = f.data;
    out.push({ key: f.file, who: `v${f.version} (Muse)`, baseline: false, suite: d.suite, gate: d.gate_name,
      gatePassed: d.gate_passed, agg: d.aggregate ?? {} });
  }
  for (const f of files) {
    const cmp = f.data.comparison ?? {};
    for (const [name, v] of Object.entries<any>(cmp)) {
      if (!name.startsWith("baseline_") || !v?.aggregate) continue;
      const k = `${f.data.suite}:${name}`;
      if (baselineDone.has(k)) continue;
      baselineDone.add(k);
      out.push({ key: `${f.file}:${name}`, who: name.replace("baseline_", ""), baseline: true, suite: f.data.suite,
        gate: "—", gatePassed: null, agg: v.aggregate });
    }
  }
  return out;
}

function MetricTable({ title, files, protocol }: { title: string; files: EvalFile[]; protocol: string | null }) {
  const rows = rowsFor(files);
  const hasPost = rows.some((r) => r.agg.median_post_disturbance_mae != null);
  if (!rows.length) return null;
  return (
    <div className="metric-block">
      <h3>
        {title}
        <span className="protocol" title="prompt/protocol version recorded in result.json">protocol {protocol ?? "—"}</span>
      </h3>
      <table className="tbl num">
        <thead>
          <tr>
            <th>controller</th>
            <th>suite</th>
            <th>gate</th>
            <th>passed</th>
            <th>median MAE</th>
            {hasPost && <th>post-change MAE</th>}
            <th>in-band</th>
            <th>energy</th>
            <th>overrides</th>
            <th>violations</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.key} className={r.baseline ? "baseline" : ""}>
              <td>
                {r.who}
                {r.baseline && <div className="tag-baseline">fixed baseline (never shown to Muse)</div>}
              </td>
              <td className={r.suite === CHANGED_MACHINE_SUITE ? "small" : "mono small"}>{suiteLabel(r.suite)}</td>
              <td>
                {r.gatePassed == null ? (
                  <span className="muted">—</span>
                ) : (
                  <span className={`chip ${r.gatePassed ? "good" : "bad"}`}>
                    {r.gate} {r.gatePassed ? "PASS" : "FAIL"}
                  </span>
                )}
              </td>
              <td className="mono">
                {fmtNum(r.agg.n_passed, 0)}/{fmtNum(r.agg.n_episodes, 0)}
              </td>
              <td className="mono">{fmtNum(r.agg.median_mae, 4)}</td>
              {hasPost && <td className="mono">{fmtNum(r.agg.median_post_disturbance_mae, 4)}</td>}
              <td className="mono">{fmtPct(r.agg.mean_in_band_fraction, 1)}</td>
              <td className="mono">{fmtNum(r.agg.median_actuation_energy, 1)}</td>
              <td className="mono">{fmtNum(r.agg.total_overrides, 0)}</td>
              <td className="mono">{fmtNum(r.agg.total_hard_violations, 0)}</td>
            </tr>
          ))}
        </tbody>
      </table>
      {files.map((f) => (
        <div key={f.file} className="reasons">
          <span className="mono small muted">{f.file}:</span>
          {(f.data.gate_reasons ?? []).map((g: string, i: number) => (
            <span key={i} className="reason">
              {g}
            </span>
          ))}
        </div>
      ))}
    </div>
  );
}

const FINAL = ["COMPLETE", "FAILED", "STOPPED"];

function TwinCompare({ before, after }: { before: Json | null; after: Json | null }) {
  if (!before || !after) return null;
  const rows: [string, string, number][] = [
    ["K (gain at u=1)", "°C", 2],
    ["tau", "s", 1],
    ["dead time", "s", 1],
    ["ambient", "°C", 1],
  ];
  const keys = ["K_c", "tau_s", "L_s", "Ta_c"];
  return (
    <div className="metric-block">
      <h3>Trusted twins used for scoring (fitted by trusted code; never shown to Muse)</h3>
      <table className="tbl num twin-tbl">
        <thead>
          <tr>
            <th>parameter</th>
            <th>original twin (twin_fit.json, discovery experiments)</th>
            <th>changed-machine twin (twin_fit_after_change.json, after-change experiments)</th>
          </tr>
        </thead>
        <tbody>
          {rows.map(([label, unit, dg], i) => (
            <tr key={label}>
              <td>{label}</td>
              <td className="mono">{fmtNum(before[keys[i]], dg)} {unit}</td>
              <td className="mono">{fmtNum(after[keys[i]], dg)} {unit}</td>
            </tr>
          ))}
          <tr>
            <td>fit RMSE</td>
            <td className="mono">{fmtNum(before.report?.rmse, 4)} (normalized y)</td>
            <td className="mono">{fmtNum(after.report?.rmse, 4)} (normalized y)</td>
          </tr>
        </tbody>
      </table>
    </div>
  );
}

function Adaptation({ files, verdicts, stage, protocol, changedSuite, twins }: { files: EvalFile[]; verdicts: RepairVerdict[]; stage: string; protocol: string | null; changedSuite: boolean; twins: React.ReactNode }) {
  const ended = FINAL.includes(stage);
  return (
    <>
      <div className="small muted">
        Promotion rule (decided 2026-10-31): Gate 3 = post-change suite, ≥ 3 scenarios improved ≥ 20% vs frozen v1 (thresholds as
        stated in each candidate's gate reasons below), zero hard violations, zero invalid outputs. Nominal G2 after repair is re-scored
        and reported, not gated.
      </div>
      {twins}
      {files.map((f) => {
        const c: Json = f.data.comparison ?? {};
        const v = verdicts.find((x) => x.version === f.version);
        const nominal = v?.nominal_after_repair_passed ?? f.data.nominal_gate;
        const rec = v?.recorded_outcome;
        return (
          <div key={f.file} className="metric-block">
            <h3>
              Repair candidate v{f.version} vs frozen v1
              <span className="protocol">protocol {protocol ?? "—"}</span>{" "}
              {changedSuite && <span className="protocol">scored on: {suiteLabel(CHANGED_MACHINE_SUITE)}</span>}{" "}
              <span className={`chip ${c.gate_passed ? "good" : "bad"}`} title="adaptation comparison gate (current promotion rule)">
                G3 {c.gate_passed ? "PASS" : "FAIL"}
              </span>{" "}
              <span className={`chip ${nominal ? "good" : "warn"}`} title={`evaluation_v${f.version}.json; reported, not gated`}>
                nominal after repair: {nominal == null ? "—" : nominal ? "PASS" : "FAIL"}
              </span>{" "}
              {ended && rec && (
                <span className={`chip ${rec.stage === "COMPLETE" ? "good" : rec.stage === "FAILED" ? "bad" : "warn"}`}
                  title={`recorded in ${rec.source}; candidate status ${v?.recorded_candidate_status ?? "—"}`}>
                  recorded: {rec.stage} · v{f.version} {v?.recorded_candidate_status ?? "—"}
                </span>
              )}
            </h3>
            {ended && rec?.reason && <div className="small muted">recorded reason: {rec.reason}</div>}
            {ended && v?.verdict_disagrees && v.note && <div className="rule-note">{v.note}</div>}
            <div className="small">
              Muse diagnosis: <span className="mono">{f.data.diagnosis_category ?? "—"}</span> ·{" "}
              {f.data.diagnosis_correct == null ? (
                "not scored"
              ) : f.data.diagnosis_correct ? (
                <span className="good-text">matched the injected family</span>
              ) : (
                <span className="bad-text">did not match the injected family</span>
              )}{" "}
              · median reduction {fmtPct(c.median_reduction, 1)} · {c.n_improved ?? "—"}/{(c.per_index ?? []).length} improved
            </div>
            <table className="tbl num">
              <thead>
                <tr>
                  <th>episode</th>
                  <th>post-change MAE v1 (frozen)</th>
                  <th>post-change MAE v{f.version}</th>
                  <th>reduction</th>
                  <th>≥ threshold</th>
                </tr>
              </thead>
              <tbody>
                {(c.per_index ?? []).map((p: Json) => (
                  <tr key={p.index}>
                    <td className="mono">{p.index}</td>
                    <td className="mono">{fmtNum(p.mae_v1, 4)}</td>
                    <td className="mono">{fmtNum(p.mae_v2, 4)}</td>
                    <td className={`mono ${Number(p.reduction) > 0 ? "good-text" : "bad-text"}`}>{fmtPct(p.reduction, 1)}</td>
                    <td>{p.improved ? "yes" : "no"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            <div className="reasons">
              {(c.reasons ?? []).map((g: string, i: number) => (
                <span key={i} className="reason">
                  {g}
                </span>
              ))}
            </div>
          </div>
        );
      })}
    </>
  );
}

function TraceCompare({ files, profile }: { files: EvalFile[]; profile: DisplayProfile }) {
  const C = isCelsius(profile);
  const D = (v: number) => toDisplay(profile, v) as number;
  const indices = useMemo(() => {
    const s = new Set<number>();
    files.forEach((f) => (f.data.episodes ?? []).forEach((e: Json) => e.trace?.steps?.length && s.add(e.index)));
    return [...s].sort((a, b) => a - b);
  }, [files]);
  const [idx, setIdx] = useState<number | null>(null);
  useEffect(() => {
    if (idx == null || !indices.includes(idx)) setIdx(indices[0] ?? null);
  }, [indices, idx]);

  const chart = useMemo(() => {
    if (idx == null) return null;
    const byT = new Map<number, Json>();
    let disturbAt: number | null = null;
    let seed: number | null = null;
    const keys: string[] = [];
    for (const f of files) {
      const ep = (f.data.episodes ?? []).find((e: Json) => e.index === idx);
      const steps: Json[] | undefined = ep?.trace?.steps;
      if (!steps) continue;
      const k = `v${f.version}`;
      keys.push(k);
      seed = ep.seed ?? seed;
      disturbAt = ep.trace.disturbance_at ?? disturbAt;
      for (const s of steps) {
        const t = Math.round(s.t * 1000) / 1000;
        const row = byT.get(t) ?? { t };
        row[k] = toDisplay(profile, s.h_true);
        byT.set(t, row);
      }
    }
    const data = downsample([...byT.values()].sort((a, b) => a.t - b.t), 2000);
    return { data, keys, disturbAt, seed };
  }, [files, idx, profile]);

  if (!indices.length) return null;
  return (
    <div className="metric-block">
      <div className="sub-head">
        <h3>
          {files.some((f) => f.data.suite === CHANGED_MACHINE_SUITE) ? "Same-scenario episode on the changed-machine twin" : "Same-seed disturbance episode"}
          {" "}· h_true (evaluator truth){C ? ", °C" : ""}
        </h3>
        <select value={idx ?? ""} onChange={(e) => setIdx(Number(e.target.value))} aria-label="Disturbance episode">
          {indices.map((i) => (
            <option key={i} value={i}>
              episode {i}
            </option>
          ))}
        </select>
        {chart?.seed != null && <span className="muted small mono">scenario {chart.seed}</span>}
      </div>
      {chart && chart.keys.length < 2 && (
        <div className="muted small">Only {chart.keys.join(", ")} has a disturbance evaluation in this run; no v2 to compare.</div>
      )}
      <div className="chart-wrap small-chart">
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={chart?.data ?? []} margin={{ top: 12, right: 8, bottom: 4, left: -8 }}>
            <CartesianGrid stroke="var(--grid)" vertical={false} />
            <XAxis dataKey="t" type="number" domain={["dataMin", "dataMax"]} tick={{ fill: "var(--muted)", fontSize: 11 }}
              tickFormatter={(v) => `${Math.round(v)}s`} stroke="var(--line)" />
            <YAxis domain={[D(0), D(1)]} tick={{ fill: "var(--muted)", fontSize: 11 }} stroke="var(--line)"
              tickFormatter={(v) => (C ? v.toFixed(0) : String(v))} />
            <ReferenceArea y1={D(profile.band[0])} y2={D(profile.band[1])} fill="var(--band)" fillOpacity={1} stroke="none" />
            <ReferenceLine y={D(profile.hard_cutoff)} stroke="var(--bad)" />
            {chart?.disturbAt != null && (
              <ReferenceLine x={chart.disturbAt} stroke="var(--bad)" strokeWidth={2}
                label={{ value: "disturbance", fill: "var(--bad)", fontSize: 10, position: "insideTopRight" }} />
            )}
            {chart?.keys.map((k, i) => (
              <Line key={k} dataKey={k} name={`${k} h_true`} stroke={SERIES_COLORS[i % 4]} dot={false} strokeWidth={1.6}
                isAnimationActive={false} />
            ))}
            <Tooltip contentStyle={{ background: "var(--panel-2)", border: "1px solid var(--line)", fontSize: 12 }}
              formatter={(v: any) => (C ? `${fmtNum(v, 2)} °C` : fmtNum(v, 3))} labelFormatter={(v) => `t=${fmtNum(v, 1)}s`} />
            <Legend wrapperStyle={{ fontSize: 11 }} />
          </LineChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}

export default function EvidencePanel({ profile = TANK_DISPLAY, evals, run, stage, events, board = null }: { profile?: DisplayProfile; evals: Evaluations | null; run: RunDetail | null; stage: string; events: RunEvent[]; board?: BoardVerification | null }) {
  const tf: Json | null = evals?.twin_fit ?? null;
  const changedSuite = !!evals?.disturbance.some((f) => f.data.suite === CHANGED_MACHINE_SUITE);
  const mon = evals?.monitoring;
  const lastStage = [...events].reverse().find((e) => e.kind === "stage");
  const any = evals && (evals.heldout.length || evals.disturbance.length || evals.adaptation.length || mon || board);
  const usage: Json | null = run?.model_usage ?? null;
  const proto = evals?.protocol?.prompt_version ?? run?.prompt_version ?? null;
  return (
    <section className="panel evidence">
      <div className="panel-head">
        <h2>Evidence</h2>
        <span className="muted small">trusted evaluator output · hidden seeds · same-seed comparisons</span>
      </div>
      {!any ? (
        <div className="empty">No evaluation recorded yet.</div>
      ) : (
        <div className="evidence-body">
          {profile.eval_plant === "twin" && (
            <div className="rule-note">
              Gates scored on a trusted digital twin fitted from the discovery experiments (twin_fit.json); physical traces are shown unscored
              {tf && (
                <div className="small muted mono">
                  twin: K {fmtNum(tf.K_c, 2)} °C · τ {fmtNum(tf.tau_s, 1)} s · dead time {fmtNum(tf.L_s, 1)} s · ambient {fmtNum(tf.Ta_c, 1)} °C ·
                  noise σ {fmtNum(tf.noise_std_c, 3)} °C · fit RMSE {fmtNum(tf.report?.rmse, 4)} (normalized y)
                </div>
              )}
            </div>
          )}
          {isCelsius(profile) && (
            <div className="small muted">
              MAE values are in normalized y; multiply by {profile.y_scale} for °C.
            </div>
          )}
          <MetricTable title="Held-out suite (nominal, hidden seeds)" files={evals!.heldout} protocol={proto} />
          {mon && (
            <div className="metric-block">
              <h3>Trusted monitor</h3>
              <div className="kv small">
                <span>
                  degraded: <b className={mon.detector?.degraded ? "warn-text" : "good-text"}>{String(!!mon.detector?.degraded)}</b>
                </span>
                <span>at t = {fmtNum(mon.degraded_at_t, 1)} s</span>
                <span>baseline window MAE {fmtNum(mon.detector?.baseline_window_mae, 4)}</span>
                <span>threshold {fmtNum(mon.detector?.threshold, 4)}</span>
                <span>recent window MAE {fmtNum(mon.detector?.recent_window_mae, 4)}</span>
                <span className="muted">{mon.detector?.degraded_reason}</span>
              </div>
            </div>
          )}
          <MetricTable title={changedSuite ? "Post-change suite · changed-machine twin (refitted from after-change experiments), same scenarios for every version" : "Post-change suite (same scenarios for every version)"} files={evals!.disturbance} protocol={proto} />
          {!evals!.adaptation.length && <TwinCompare before={tf} after={evals!.twin_fit_after_change} />}
          {evals!.adaptation.length ? (
            <Adaptation files={evals!.adaptation} verdicts={evals!.repair_verdicts} stage={stage} protocol={proto}
              changedSuite={changedSuite} twins={<TwinCompare before={tf} after={evals!.twin_fit_after_change} />} />
          ) : mon ? (
            <div className="metric-block">
              <h3>Adaptation</h3>
              <div className="muted small">
                No adaptation recorded. Run ended {stage}
                {lastStage?.reason ? `: ${lastStage.reason}` : ""}.
              </div>
            </div>
          ) : null}
          {board && <BoardVerificationPanel bv={board} profile={profile} />}
          <TraceCompare files={evals!.disturbance} profile={profile} />
          {usage && ["DEPLOYABLE", "COMPLETE", "FAILED", "STOPPED"].includes(stage) && (
            <div className="muted small">
              result.json model usage: {usage.calls} attempts ({usage.failed_calls} failed) · reasoning tokens{" "}
              {usage.reasoning_tokens} · est. ${fmtNum(usage.cost_usd, 3)}
            </div>
          )}
        </div>
      )}
    </section>
  );
}
