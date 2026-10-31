import { useMemo } from "react";
import {
  CartesianGrid,
  ComposedChart,
  Legend,
  Line,
  ReferenceArea,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { Json, RunEvent } from "../api";
import { downsample, fmtNum } from "../format";

interface Pt {
  t: number;
  y: number | null;
  u: number | null;
  override?: boolean;
  phase: "experiment" | "monitoring" | "after_change" | "gap";
  src_t?: number;
}

const MAX_POINTS = 2000;
const GAP_S = 6;

export default function PlantPanel({ events, monitoring, replay }: { events: RunEvent[]; monitoring: Json | null; replay: boolean }) {
  const d = useMemo(() => {
    const exps = events.filter((e) => e.kind === "experiment_result" && Array.isArray(e.samples) && e.samples.length);
    const isAfter = (e: RunEvent) => e.phase === "after_change";
    const expPts: Pt[] = [];
    const bounds: { t: number; label: string; after: boolean }[] = [];
    const push = (e: RunEvent, off: number, into: Pt[], phase: Pt["phase"]) => {
      const s = e.samples as Json[];
      bounds.push({ t: s[0].t + off, label: `${e.experiment_id} u=${fmtNum(s[0].u_requested, 2)}`, after: phase === "after_change" });
      for (const x of s) into.push({ t: x.t + off, src_t: x.t, y: x.y, u: x.u_applied, override: !!x.override, phase });
    };
    for (const e of exps.filter((x) => !isAfter(x))) push(e, 0, expPts, "experiment");
    expPts.sort((a, b) => a.t - b.t);
    const expEnd = expPts.length ? expPts[expPts.length - 1].t : 0;

    let monPts: Pt[] = [];
    let monStart: number | null = null;
    let monOff = 0;
    let disturbAt: number | null = null;
    let detectAt: number | null = null;
    const steps: Json[] | undefined = monitoring?.trace?.steps;
    if (steps && steps.length) {
      monOff = (expPts.length ? expEnd + GAP_S : 0) - steps[0].t;
      monStart = steps[0].t + monOff;
      if (monitoring?.trace?.disturbance_at != null) disturbAt = monitoring.trace.disturbance_at + monOff;
      if (monitoring?.degraded_at_t != null) detectAt = monitoring.degraded_at_t + monOff;
      monPts = steps.map((x) => ({ t: x.t + monOff, src_t: x.t, y: x.y, u: x.u_applied, override: !!x.override, phase: "monitoring" as const }));
    }

    // Re-identification experiments run on the changed machine after the monitored rollout, on the
    // same plant clock, so they share the rollout's offset. Without a rollout, place them after a gap.
    const afterExps = exps.filter(isAfter);
    const afterPts: Pt[] = [];
    let afterStart: number | null = null;
    if (afterExps.length) {
      const first = (afterExps[0].samples as Json[])[0].t;
      const lastBefore = monPts.length ? monPts[monPts.length - 1].t : expEnd;
      const off = monPts.length && first + monOff >= lastBefore ? monOff : lastBefore + GAP_S - first;
      for (const e of afterExps) push(e, off, afterPts, "after_change");
      afterPts.sort((a, b) => a.t - b.t);
      afterStart = afterPts[0].t;
    }

    const fixed = expPts.length + afterPts.length;
    const monDs = downsample(monPts, Math.max(200, MAX_POINTS - fixed), (p) => !!p.override);
    const gap = (t: number): Pt => ({ t, y: null, u: null, phase: "gap" });
    const parts: Pt[] = [...expPts];
    if (expPts.length && monDs.length) parts.push(gap(expEnd + GAP_S / 2));
    parts.push(...monDs);
    if (afterPts.length && parts.length) {
      const prevEnd = parts[parts.length - 1].t;
      if (afterPts[0].t - prevEnd > 0.15) parts.push(gap((prevEnd + afterPts[0].t) / 2));
    }
    parts.push(...afterPts);
    const data = downsample(parts, MAX_POINTS, (p) => p.phase === "gap" || !!p.override);
    const all = [...expPts, ...monPts, ...afterPts];
    const overrides = all.filter((p) => p.override).length;
    return { data, bounds, monStart, disturbAt, detectAt, afterStart, overrides, nRaw: all.length };
  }, [events, monitoring]);

  return (
    <section className="panel plant">
      <div className="panel-head">
        <h2>Plant</h2>
        <span className="badge sim">SIMULATED</span>
        {replay && <span className="badge replay">REPLAY</span>}
        <span className="muted small">
          {d.data.length ? `${d.nRaw} stored samples (showing ${d.data.length}) · overrides ${d.overrides}` : ""}
        </span>
      </div>
      {d.data.length === 0 ? (
        <div className="empty">No experiment samples recorded yet.</div>
      ) : (
        <div className="chart-wrap">
          <ResponsiveContainer width="100%" height="100%">
            <ComposedChart data={d.data} margin={{ top: 22, right: 8, bottom: 4, left: -8 }}>
              <CartesianGrid stroke="var(--grid)" vertical={false} />
              <XAxis dataKey="t" type="number" domain={["dataMin", "dataMax"]} tick={{ fill: "var(--muted)", fontSize: 11 }}
                tickFormatter={(v) => `${Math.round(v)}s`} stroke="var(--line)" />
              <YAxis yAxisId="y" domain={[0, 1]} ticks={[0, 0.2, 0.4, 0.6, 0.8, 1]} tick={{ fill: "var(--muted)", fontSize: 11 }} stroke="var(--line)"
                tickFormatter={(v) => v.toFixed(1)} />
              <YAxis yAxisId="u" orientation="right" domain={[0, 1]} ticks={[0, 0.2, 0.4, 0.6, 0.8, 1]} tick={{ fill: "var(--muted)", fontSize: 11 }}
                stroke="var(--line)" tickFormatter={(v) => v.toFixed(1)} />
              <ReferenceArea yAxisId="y" y1={0.55} y2={0.65} fill="var(--band)" fillOpacity={1} stroke="none" />
              <ReferenceLine yAxisId="y" y={0.85} stroke="var(--warn)" strokeDasharray="4 4"
                label={{ value: "soft 0.85", fill: "var(--warn)", fontSize: 10, position: "insideTopLeft" }} />
              <ReferenceLine yAxisId="y" y={0.9} stroke="var(--bad)"
                label={{ value: "hard cutoff 0.90", fill: "var(--bad)", fontSize: 10, position: "insideTopRight" }} />
              {d.bounds.map((b, i) => (
                <ReferenceLine key={b.label} yAxisId="y" x={b.t} stroke="var(--line-strong)" strokeDasharray="2 3"
                  label={(props: any) => {
                    const vb = props.viewBox ?? {};
                    const [id, u] = b.label.split(" ");
                    const y = (vb.y ?? 0) + (vb.height ?? 0) - 6 - (i % 2) * 13;
                    return (
                      <g>
                        <text x={(vb.x ?? 0) + 3} y={y} fill={b.after ? "var(--s2)" : "var(--text)"} fontSize={10} fontFamily="var(--mono)">
                          <title>{`${id} constant ${u}`}</title>
                          {id}
                        </text>
                      </g>
                    );
                  }} />
              ))}
              {d.monStart != null && (
                <ReferenceLine yAxisId="y" x={d.monStart} stroke="var(--accent)"
                  label={{ value: "monitored rollout (plant reset)", fill: "var(--accent)", fontSize: 10, position: "top" }} />
              )}
              {d.disturbAt != null && (
                <ReferenceLine yAxisId="y" x={d.disturbAt} stroke="var(--bad)" strokeWidth={2}
                  label={{ value: "hidden disturbance", fill: "var(--bad)", fontSize: 10, position: "insideTopRight" }} />
              )}
              {d.afterStart != null && (
                <ReferenceLine yAxisId="y" x={d.afterStart} stroke="var(--s2)" strokeWidth={2}
                  label={{ value: "re-identification on the changed machine", fill: "var(--s2)", fontSize: 10, position: "insideTopLeft" }} />
              )}
              {d.detectAt != null && (
                <ReferenceLine yAxisId="y" x={d.detectAt} stroke="var(--warn)" strokeWidth={2}
                  label={{ value: "degradation detected", fill: "var(--warn)", fontSize: 10, position: "insideBottomRight" }} />
              )}
              <Line yAxisId="u" dataKey="u" name="pump duty u_applied" type="stepAfter" stroke="var(--u)" strokeWidth={1}
                dot={false} isAnimationActive={false} connectNulls={false} />
              <Line yAxisId="y" dataKey="y" name="level y (measured)" stroke="var(--y)" strokeWidth={1.6} dot={false}
                isAnimationActive={false} connectNulls={false} />
              <Tooltip contentStyle={{ background: "var(--panel-2)", border: "1px solid var(--line)", fontSize: 12 }}
                labelFormatter={(v, p) => {
                  const pt = p?.[0]?.payload as Pt | undefined;
                  if (pt?.phase === "monitoring") return `monitored rollout t=${fmtNum(pt.src_t, 1)}s`;
                  if (pt?.phase === "after_change") return `re-identification (changed machine) t=${fmtNum(pt.src_t, 1)}s`;
                  return `t=${fmtNum(v, 1)}s`;
                }}
                formatter={(v: any) => fmtNum(v, 3)} />
              <Legend wrapperStyle={{ fontSize: 11, color: "var(--muted)" }} />
            </ComposedChart>
          </ResponsiveContainer>
        </div>
      )}
      {d.bounds.length > 0 && (
        <div className="exp-legend mono small">
          {d.bounds.map((b) => (
            <span key={b.label} className={b.after ? "after-text" : ""}>
              {b.label}
              {b.after ? " (after change)" : ""}
            </span>
          ))}
        </div>
      )}
      <div className="caption">
        Band 0.55–0.65 shaded. Experiments use the agent-safe samples recorded in each <code>experiment_result</code>{" "}
        event; the monitored rollout is <code>monitoring.json</code> (a fresh rollout from reset, placed after the
        experiments on this axis). After-change re-identification experiments continue on the changed machine's
        clock after the rollout.
      </div>
    </section>
  );
}
