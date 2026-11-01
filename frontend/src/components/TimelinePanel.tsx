import { useEffect, useMemo, useRef, useState } from "react";
import { fmtY, TANK_DISPLAY, type DisplayProfile, type ExperimentFacts, type Json, type RunEvent } from "../api";
import { fmtNum, fmtPct, fmtRel, fmtUsd, short } from "../format";

const ICON: Record<string, string> = {
  run_started: "▶",
  stage: "◆",
  model_call: "◇",
  ledger: "≡",
  experiment_proposed: "?",
  experiment_result: "∿",
  readiness_refused: "⊘",
  ready_to_generate: "✓",
  ready_to_revise: "✓",
  twin_fitted: "≈",
  changed_twin_fitted: "≈",
  changed_twin_skipped: "⊘",
  operator_disturbance_prompt: "☞",
  operator_disturbance_applied: "⚡",
  reidentification_budget_exhausted: "⌛",
  exploration_budget_exhausted: "⌛",
  candidate_registered: "⌗",
  static_check: "⊢",
  sandbox_check: "▣",
  evaluation: "Σ",
  candidate_approved: "✔",
  candidate_failed_gate: "✕",
  disturbance_scheduled: "⚡",
  monitoring_result: "◎",
  adaptation_result: "↻",
  error: "!",
};

function tone(e: RunEvent): string {
  switch (e.kind) {
    case "error":
    case "candidate_failed_gate":
    case "readiness_refused":
      return "bad";
    case "candidate_approved":
    case "ready_to_generate":
    case "ready_to_revise":
      return "good";
    case "static_check":
    case "sandbox_check":
      return e.ok ? "good" : "bad";
    case "evaluation":
      return e.gate_passed ? "good" : "bad";
    case "adaptation_result":
      return e.gate3_passed ? "good" : "bad";
    case "experiment_proposed":
      return e.verdict_ok ? "info" : "bad";
    case "monitoring_result":
      return e.degraded ? "warn" : "good";
    case "disturbance_scheduled":
    case "operator_disturbance_prompt":
    case "operator_disturbance_applied":
      return "warn";
    case "twin_fitted":
    case "changed_twin_fitted":
      return "info";
    case "changed_twin_skipped":
      return "warn";
    case "stage":
      return e.to === "FAILED" ? "bad" : e.to === "STOPPED" ? "warn" : "neutral";
    case "model_call":
      return e.ok === false ? "bad" : "neutral";
    default:
      return "neutral";
  }
}

const PF = (ok: unknown) => (ok ? "PASS" : "FAIL");

function summary(e: RunEvent, facts?: Map<string, ExperimentFacts>, prof: DisplayProfile = TANK_DISPLAY): { title: string; lines: string[] } {
  const L: string[] = [];
  switch (e.kind) {
    case "run_started":
      return { title: `run started · ${e.model}`, lines: [`prompt ${e.prompt_version} (${e.prompt_hash}) · agent ${e.agent_mode} · sandbox ${e.sandbox_mode}`] };
    case "stage":
      if (e.reidentifying) L.push("re-identifying the changed machine before repair");
      if (e.attempt != null && e.to === "ADAPTING" && !e.reidentifying) L.push(`repair attempt ${e.attempt}`);
      if (e.reason) L.push(String(e.reason));
      if (e.candidate_id) L.push(String(e.candidate_id));
      return { title: `${e.from} → ${e.to}`, lines: L };
    case "model_call":
      return {
        title: `model call · ${e.call_stage} · ${e.model}${e.ok === false ? " · FAILED" : ""}`,
        lines: [`${fmtNum(e.latency_s, 1)} s · in ${e.prompt_tokens} · out ${e.completion_tokens} · reasoning ${e.reasoning_tokens} tok · ${fmtUsd(Number(e.cost_usd || 0))}`],
      };
    case "ledger":
      if (e.operator_note) L.push(`“${e.operator_note}”`);
      return { title: `ledger revised · ${(e.hypotheses ?? []).length} hypotheses`, lines: L };
    case "experiment_proposed":
      if (e.operator_note) L.push(`“${e.operator_note}”`);
      if (e.uncertainty) L.push(`targets: ${e.uncertainty}`);
      if (e.safety_argument) L.push(`safety argument: ${e.safety_argument}`);
      L.push(`supervisor: ${e.verdict_ok ? "approved" : "REJECTED"} · ${e.verdict}`);
      return { title: `${e.experiment_id} proposed · u=${fmtNum(e.command_u, 2)} for ${fmtNum(e.duration_s, 1)} s`, lines: L };
    case "experiment_result": {
      L.push(prof.y_unit === "°C"
        ? `${fmtY(prof, e.y_start, 2)} → ${fmtY(prof, e.y_end, 2)} (y ${fmtNum(e.y_start, 3)} → ${fmtNum(e.y_end, 3)}) · ${e.n_samples} steps · overrides ${e.overrides}`
        : `y ${fmtNum(e.y_start, 3)} → ${fmtNum(e.y_end, 3)} · ${e.n_samples} steps · overrides ${e.overrides}`);
      const f = facts?.get(String(e.experiment_id));
      if (f && (f.command_before != null || f.seconds_since_command_last_changed_at_start != null))
        L.push(`trusted: command before ${fmtNum(f.command_before, 2)} · ${fmtNum(f.seconds_since_command_last_changed_at_start, 1)} s since last command change`);
      return { title: `${e.experiment_id} ${e.status}`, lines: L };
    }
    case "readiness_refused":
      return { title: "readiness refused by trusted gate", lines: [String(e.reason), e.justification ? `Muse: ${e.justification}` : ""].filter(Boolean) };
    case "ready_to_generate":
      return { title: "ready to author controller", lines: e.justification ? [`Muse: ${e.justification}`] : [] };
    case "exploration_budget_exhausted":
      return { title: "experiment budget exhausted", lines: [] };
    case "ready_to_revise":
      return { title: "ready to author the repair", lines: e.justification ? [`Muse: ${e.justification}`] : [] };
    case "reidentification_budget_exhausted":
      return { title: "re-identification budget exhausted", lines: [] };
    case "candidate_registered":
      if (e.operator_note) L.push(`“${e.operator_note}”`);
      L.push(`sha256 ${short(e.sha256)} · ${e.byte_length} bytes${e.parent_id ? ` · parent ${e.parent_id}` : ""}`);
      if (e.diagnosis_category) L.push(`diagnosis: ${e.diagnosis_category}`);
      return { title: `controller v${e.version} registered (${e.submission_kind})`, lines: L };
    case "static_check":
      return { title: `static check ${PF(e.ok)}`, lines: (e.violations ?? []).map(String) };
    case "sandbox_check":
      return { title: `sandbox interface tests ${PF(e.ok)}`, lines: (e.detail ?? []).map(String) };
    case "evaluation": {
      const a: Json = e.aggregate ?? {};
      if (e.scored_on === "changed_machine_twin") L.push("scored on the changed-machine twin (refitted from after-change experiments)");
      L.push(`${a.n_passed ?? "—"}/${a.n_episodes ?? "—"} episodes passed · median MAE ${fmtNum(a.median_mae, 4)} · in-band ${fmtPct(a.mean_in_band_fraction)}`);
      for (const r of e.reasons ?? []) L.push(String(r));
      return { title: `evaluation · ${e.suite} · ${e.gate} ${PF(e.gate_passed)}`, lines: L };
    }
    case "candidate_approved":
      return { title: `approved · ${e.candidate_id}`, lines: [] };
    case "candidate_failed_gate":
      return { title: `failed gate · ${e.candidate_id}`, lines: (e.reasons ?? []).map(String) };
    case "disturbance_scheduled":
      return {
        title: !e.scheduled ? "monitoring without disturbance" : e.operator_applied ? "operator-applied physical change expected" : "hidden disturbance scheduled",
        lines: ["family is not recorded in events"],
      };
    case "twin_fitted": {
      const r: Json = e.report ?? {};
      L.push(`fitted by trusted code from ${e.n_traces} discovery traces · RMSE ${fmtNum(r.rmse, 4)} (normalized y) over ${r.n_points ?? "—"} points`);
      L.push("used only to score gates; never shown to Muse");
      return { title: "digital twin fitted", lines: L };
    }
    case "changed_twin_fitted": {
      const r: Json = e.report ?? {};
      L.push(`refitted by trusted code from ${e.n_traces} after-change experiments · RMSE ${fmtNum(r.rmse, 4)} (normalized y) over ${r.n_points ?? "—"} points`);
      L.push("repairs are scored on this changed-machine twin; never shown to Muse");
      for (const w of r.warnings ?? []) L.push(`warning: ${w}`);
      return { title: "changed-machine twin fitted", lines: L };
    }
    case "changed_twin_skipped":
      return { title: "changed-machine twin not fitted", lines: [String(e.reason ?? "")] };
    case "operator_disturbance_prompt":
      return { title: "operator prompted to apply the physical change", lines: e.note ? [String(e.note)] : [] };
    case "operator_disturbance_applied":
      return { title: "operator confirmed the physical change", lines: ["family is not recorded in events"] };
    case "monitoring_result":
      return {
        title: e.degraded ? `degradation detected at t=${fmtNum(e.degraded_at_t, 1)} s` : "no degradation detected",
        lines: e.detector ? [`window MAE ${fmtNum(e.detector.baseline_window_mae, 4)} → ${fmtNum(e.detector.recent_window_mae, 4)} (threshold ${fmtNum(e.detector.threshold, 4)})`] : [],
      };
    case "adaptation_result":
      return {
        title: `adaptation · G3 ${PF(e.gate3_passed)} · ${e.candidate_id}`,
        lines: [`${e.n_improved} improved · median reduction ${fmtPct(e.median_reduction, 1)} · nominal gate ${PF(e.nominal_gate_passed)} · diagnosis ${e.diagnosis_correct == null ? "—" : e.diagnosis_correct ? "matched" : "did not match"}`],
      };
    case "error":
      return { title: "error", lines: [String(e.error ?? ""), ...(e.leaks ?? []).map(String)] };
    default:
      return { title: e.kind, lines: [] };
  }
}

function LedgerTable({ events }: { events: RunEvent[] }) {
  const ledgers = useMemo(() => events.filter((e) => e.kind === "ledger"), [events]);
  const afterChange = ledgers.length > 0 && ledgers[ledgers.length - 1].phase === "after_change";
  if (!ledgers.length) return <div className="empty small">No ledger revisions yet.</div>;
  const cur = ledgers[ledgers.length - 1];
  const prev = ledgers.length > 1 ? ledgers[ledgers.length - 2] : null;
  const prevConf = new Map<string, number>((prev?.hypotheses ?? []).map((h: Json) => [h.id, Number(h.confidence)]));
  const afterExp = events.filter((e) => e.kind === "experiment_result" && e.seq < cur.seq).pop()?.experiment_id;
  return (
    <div className="ledger">
      <div className="sub-head">
        <h3>Hypothesis ledger</h3>
        <span className="muted small">
          revision {ledgers.length} · {afterExp ? `after ${afterExp}` : "before any experiment"} · seq {cur.seq}
        </span>
        {afterChange && <span className="badge after">after change</span>}
      </div>
      <table className="tbl">
        <thead>
          <tr>
            <th>id</th>
            <th>statement</th>
            <th style={{ width: 130 }}>confidence</th>
            <th>evidence</th>
          </tr>
        </thead>
        <tbody>
          {(cur.hypotheses ?? []).map((h: Json) => {
            const c = Number(h.confidence);
            const p = prevConf.get(h.id);
            const delta = p == null ? null : c - p;
            return (
              <tr key={h.id}>
                <td className="mono">{h.id}</td>
                <td>{h.statement}</td>
                <td>
                  <div className="conf">
                    <div className="bar">
                      <div style={{ width: `${Math.max(0, Math.min(1, c)) * 100}%` }} />
                    </div>
                    <span className="mono small">{fmtNum(c, 2)}</span>
                    {delta != null && Math.abs(delta) > 1e-9 && (
                      <span className={`mono small ${delta > 0 ? "good-text" : "bad-text"}`}>
                        {delta > 0 ? "+" : ""}
                        {delta.toFixed(2)}
                      </span>
                    )}
                    {p == null && prev && <span className="small info-text">new</span>}
                  </div>
                </td>
                <td className="mono small">{(h.evidence_refs ?? []).join(" ") || "—"}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

export default function TimelinePanel({ events, facts, profile }: { events: RunEvent[]; facts: ExperimentFacts[]; profile: DisplayProfile }) {
  const factMap = useMemo(() => new Map(facts.map((f) => [f.id, f])), [facts]);
  const listRef = useRef<HTMLOListElement>(null);
  const [follow, setFollow] = useState(true);
  const t0 = events.length ? events[0].ts : 0;

  useEffect(() => {
    const el = listRef.current;
    if (el && follow) el.scrollTop = el.scrollHeight;
  }, [events.length, follow]);

  return (
    <section className="panel timeline">
      <div className="panel-head">
        <h2>Agent timeline</h2>
        <span className="muted small">{events.length} events</span>
        <label className="small muted follow">
          <input type="checkbox" checked={follow} onChange={(e) => setFollow(e.target.checked)} /> follow
        </label>
      </div>
      <ol className="events" ref={listRef}>
        {events.map((e) => {
          const s = summary(e, factMap, profile);
          return (
            <li key={e.seq} className={`ev ${tone(e)}`}>
              <span className="ev-time mono">{fmtRel(e.ts - t0)}</span>
              <span className={`ev-icon ${tone(e)}`} aria-hidden>
                {ICON[e.kind] ?? "·"}
              </span>
              <div className="ev-body">
                <div className="ev-title">
                  {s.title}
                  <span className="ev-kind mono">{e.kind}</span>
                  {e.stage && e.kind !== "stage" && <span className="ev-stage mono">{e.stage}</span>}
                  {e.phase === "after_change" && <span className="badge after">after change</span>}
                </div>
                {s.lines.map((l, i) => (
                  <div key={i} className="ev-line">
                    {l}
                  </div>
                ))}
                <details>
                  <summary>raw JSON · seq {e.seq}</summary>
                  <pre>{JSON.stringify(e, null, 1)}</pre>
                </details>
              </div>
            </li>
          );
        })}
      </ol>
      <LedgerTable events={events} />
    </section>
  );
}
