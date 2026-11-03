import { useMemo, useState } from "react";
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
import { isCelsius, toDisplay, toDisplayDelta, type BoardTrial, type BoardVerification, type DisplayProfile, type Json } from "../api";
import { downsample, fmtNum, fmtPct, short } from "../format";

// board_verification.json, rendered as stored. Only unit conversion (profile y_scale/y_offset) and percent formatting.
const COLORS: Record<string, string> = { v1: "var(--s1)", v2: "var(--s2)" };
const colorOf = (label: string, i: number) => COLORS[label] ?? ["var(--s3)", "var(--s4)"][i % 2];

const APPLIED_BY: Record<string, string> = {
  trusted_actuator: "applied by trusted code at the actuator",
  operator: "applied by the operator",
};

function Interlock({ hit }: { hit: boolean | null | undefined }) {
  if (hit == null) return <span className="muted">—</span>;
  return <span className={`chip ${hit ? "bad" : "good"}`}>{hit ? "TRIPPED" : "not hit"}</span>;
}

export default function BoardVerificationPanel({ bv, profile }: { bv: BoardVerification; profile: DisplayProfile }) {
  const C = isCelsius(profile);
  const unit = C ? "°C" : profile.y_unit;
  const [showTwin, setShowTwin] = useState(true);
  const pvb: Json = bv.prediction_vs_board ?? {};
  const { order, trials, twinTrials } = useMemo(() => {
    const order = bv.order?.length ? bv.order : bv.trials.map((t) => t.label);
    const trials = order.map((l) => bv.trials.find((t) => t.label === l)).filter((t): t is BoardTrial => !!t);
    return { order, trials, twinTrials: bv.twin_prediction?.trials ?? [] };
  }, [bv]);
  const basis = bv.prediction_basis ?? bv.twin_prediction?.prediction_basis ?? null;
  const dist = bv.disturbance ?? ({} as BoardVerification["disturbance"]);
  const mae = (v: unknown) => fmtNum(toDisplayDelta(profile, v as number), 3);

  const predicted = (label: string): unknown =>
    twinTrials.find((t) => t.label === label)?.post_mae ?? pvb[`post_mae_${label}`]?.predicted;
  const redPred = pvb.reduction?.predicted ?? bv.twin_prediction?.comparison?.reduction;
  const redMeas = pvb.reduction?.measured ?? bv.comparison?.reduction;
  const agrees: boolean | undefined = pvb.direction_agrees;

  const chart = useMemo(() => {
    const byT = new Map<number, Json>();
    const add = (ts: BoardTrial[], suffix: string, field: "y" | "h_true") => {
      for (const tr of ts) {
        for (const s of tr.trace?.steps ?? []) {
          const t = Math.round(s.t * 1000) / 1000;
          const row = byT.get(t) ?? { t };
          row[`${tr.label}${suffix}`] = toDisplay(profile, s[field]);
          byT.set(t, row);
        }
      }
    };
    add(trials, "_board", "y");
    add(twinTrials, "_twin", "h_true");
    return downsample([...byT.values()].sort((a, b) => a.t - b.t), 2000);
  }, [trials, twinTrials, profile]);

  const changeLabel = `${dist.family ?? "operator change"} @ ${fmtNum(bv.pre_s, 0)} s`;
  return (
    <div className="metric-block">
      <h3>
        Measured on the board · frozen v1 vs promoted v2 under the same change
        <span className="protocol" title="trusted artifact written after the hardware run">board_verification.json</span>{" "}
        {bv.fake_board && (
          <span className="chip bad" title="fake_board: true in board_verification.json">FAKE BOARD</span>
        )}
      </h3>
      {bv.fake_board && (
        <div className="banner" role="note">
          <span>
            <b>FAKE BOARD.</b> board_verification.json records fake_board: true. These trials did not run on the physical board.
          </span>
        </div>
      )}
      <div className="kv small">
        <span>
          change: <span className="mono">{dist.family ?? "—"}</span>
        </span>
        <span>
          magnitude: <span className="mono">{dist.magnitude == null ? "—" : String(dist.magnitude)}</span>
        </span>
        <span>{APPLIED_BY[dist.applied_by] ?? `applied by ${dist.applied_by ?? "—"}`}</span>
        <span>
          order: <span className="mono">{order.join(" → ")}</span>
        </span>
        <span>
          pre {fmtNum(bv.pre_s, 0)} s / post {fmtNum(bv.post_s, 0)} s
        </span>
        {trials.some((t) => t.start_T_display != null) && (
          <span className="muted">
            start T{" "}
            {trials.map((t) => `${t.label} ${fmtNum(t.start_T_display, 1)}${C ? " °C" : ""}`).join(" · ")}
          </span>
        )}
      </div>
      <table className="tbl num">
        <thead>
          <tr>
            <th>controller</th>
            <th>twin-predicted post-change MAE ({unit})</th>
            <th>board-measured post-change MAE ({unit})</th>
            <th>in-band (board)</th>
            <th>overrides</th>
            <th>hard violations</th>
            <th>interlock</th>
          </tr>
        </thead>
        <tbody>
          {trials.map((t) => (
            <tr key={t.label}>
              <td>
                {t.label}
                <div className="mono small muted" title={t.controller_sha256}>sha256 {short(t.controller_sha256, 12)}</div>
              </td>
              <td className="mono">{bv.twin_prediction || pvb[`post_mae_${t.label}`] ? mae(predicted(t.label)) : "—"}</td>
              <td className="mono">{mae(t.post_mae)}</td>
              <td className="mono">{fmtPct(t.post_in_band, 1)}</td>
              <td className="mono">{fmtNum(t.overrides, 0)}</td>
              <td className="mono">{fmtNum(t.hard_violations, 0)}</td>
              <td>
                <Interlock hit={t.interlock_hit} />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      <div className="small" style={{ marginTop: 6 }}>
        reduction: twin predicted <span className="mono">{fmtPct(redPred, 1)}</span>, board measured{" "}
        <span className="mono">{fmtPct(redMeas, 1)}</span>{" "}
        {agrees != null && (
          <span className={`chip ${agrees ? "good" : "bad"}`} title={pvb.direction_definition ?? "sign(predicted reduction) == sign(measured reduction)"}>
            direction {agrees ? "agrees" : "disagrees"}
          </span>
        )}
      </div>
      <div className="small muted">
        {basis ? <>prediction basis: {basis}</> : bv.twin_prediction ? null : <>no twin prediction{bv.twin_prediction_reason ? `: ${bv.twin_prediction_reason}` : ""}</>}
      </div>
      <div className="sub-head" style={{ marginTop: 8 }}>
        <h3>
          Board traces · sensor T{C ? ", °C" : ""}
        </h3>
        {twinTrials.length > 0 && (
          <label className="small muted follow">
            <input type="checkbox" checked={showTwin} onChange={(e) => setShowTwin(e.target.checked)} /> twin-predicted (dashed)
          </label>
        )}
      </div>
      <div className="chart-wrap small-chart">
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={chart} margin={{ top: 12, right: 8, bottom: 4, left: -8 }}>
            <CartesianGrid stroke="var(--grid)" vertical={false} />
            <XAxis dataKey="t" type="number" domain={["dataMin", "dataMax"]} tick={{ fill: "var(--muted)", fontSize: 11 }}
              tickFormatter={(v) => `${Math.round(v)}s`} stroke="var(--line)" />
            <YAxis domain={[(m: number) => Math.floor(m - 2), (M: number) => Math.ceil(M + 2)]} tick={{ fill: "var(--muted)", fontSize: 11 }}
              stroke="var(--line)" tickFormatter={(v) => (C ? Number(v).toFixed(0) : String(v))} />
            <ReferenceArea y1={toDisplay(profile, profile.band[0]) as number} y2={toDisplay(profile, profile.band[1]) as number}
              fill="var(--band)" fillOpacity={1} stroke="none" />
            <ReferenceLine x={bv.pre_s} stroke="var(--bad)" strokeWidth={2}
              label={{ value: changeLabel, fill: "var(--bad)", fontSize: 10, position: "insideTopRight" }} />
            {trials.map((t, i) => (
              <Line key={`${t.label}_board`} dataKey={`${t.label}_board`} name={`${t.label} board`} stroke={colorOf(t.label, i)}
                dot={false} strokeWidth={1.6} isAnimationActive={false} connectNulls />
            ))}
            {showTwin &&
              twinTrials.map((t, i) => (
                <Line key={`${t.label}_twin`} dataKey={`${t.label}_twin`} name={`${t.label} twin-predicted`} stroke={colorOf(t.label, i)}
                  strokeDasharray="5 4" strokeOpacity={0.75} dot={false} strokeWidth={1.2} isAnimationActive={false} connectNulls />
              ))}
            <Tooltip contentStyle={{ background: "var(--panel-2)", border: "1px solid var(--line)", fontSize: 12 }}
              formatter={(v: any) => (C ? `${fmtNum(v, 2)} °C` : fmtNum(v, 3))} labelFormatter={(v) => `t=${fmtNum(v, 1)}s`} />
            <Legend wrapperStyle={{ fontSize: 11 }} />
          </LineChart>
        </ResponsiveContainer>
      </div>
      <div className="caption">
        Board: stored sensor y per tick (on hardware the evaluator scores the sensor reading). Twin: stored h_true of the protocol-matched
        twin trials. Band {fmtNum(toDisplay(profile, profile.band[0]), 1)}–{fmtNum(toDisplay(profile, profile.band[1]), 1)}
        {C ? " °C" : ""}. MAE in {unit} = stored normalized MAE × {profile.y_scale}.
      </div>
    </div>
  );
}
