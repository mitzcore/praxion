import { fmtY, isCelsius, profileLabel, type DisplayProfile, type Health, type RunDetail, type RunEvent, type RunListing } from "../api";
import type { Mode } from "../App";
import { fmtDate, fmtDuration, fmtUsd } from "../format";

interface Props {
  runs: RunListing[];
  selected: string | null;
  onSelect: (id: string) => void;
  mode: Mode;
  run: RunDetail | null;
  runStarted: RunEvent | undefined;
  health: Health | null;
  stage: string;
  elapsed: number;
  cost: number;
  nCalls: number;
  recordedAt: number | null;
  profile: DisplayProfile | null;
}

const stageTone = (s: string) =>
  s === "FAILED" ? "bad" : s === "STOPPED" ? "warn" : s === "COMPLETE" || s === "DEPLOYABLE" ? "good" : "info";

export default function Header(p: Props) {
  const agentMode = (p.runStarted?.agent_mode ?? p.run?.agent_mode ?? "").toString();
  const model = p.runStarted?.model ?? p.run?.model_id ?? "—";
  // result.json is the run's own record of its protocol; run_started carries the same value.
  const pv = p.run?.prompt_version ?? p.runStarted?.prompt_version ?? "—";
  const ph = p.run?.prompt_hash ?? p.runStarted?.prompt_hash ?? null;
  const sandbox = p.runStarted?.sandbox_mode ?? p.run?.sandbox_mode ?? null;
  const replay = p.mode.kind === "replay";
  return (
    <header className="header">
      <div className="brand">
        <span className="logo" aria-hidden>
          ◬
        </span>
        <span>Praxion</span>
        <span className="muted small">evidence</span>
      </div>
      <label className="run-select">
        <span className="sr-only">Run</span>
        <select value={p.selected ?? ""} onChange={(e) => p.onSelect(e.target.value)}>
          {p.runs.map((r) => (
            <option key={r.id} value={r.id}>
              {r.id} · {r.stage}
              {r.agent_mode === "mock" ? " · MOCK" : ""}
              {r.active ? " · running" : ""}
            </option>
          ))}
        </select>
      </label>
      <div className="badges">
        {replay && (
          <span className="badge replay" title={`Re-emitting the stored event log at recorded pacing; recorded ${fmtDate(p.recordedAt)}`}>
            REPLAY {p.mode.kind === "replay" ? p.mode.speed : 1}x · {p.selected} · rec.{" "}
            {p.recordedAt ? new Date(p.recordedAt * 1000).toLocaleString(undefined, { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" }) : "—"}
          </span>
        )}
        {agentMode === "live" && <span className="badge live">LIVE MUSE</span>}
        {agentMode === "mock" && (
          <span className="badge mock" title="Mock agent: CI plumbing only, not model output">
            MOCK · not model output
          </span>
        )}
        <span className={`chip ${stageTone(p.stage)}`}>{p.stage}</span>
        {p.profile && p.profile.source !== "default_tank" && (
          <span className="badge plant-chip" title={`plant profile ${p.profile.name} (from ${p.profile.source}); y_unit ${p.profile.y_unit}`}>
            {profileLabel(p.profile)} · {isCelsius(p.profile) ? fmtY(p.profile, p.profile.target, 1) : p.profile.target.toFixed(2)} target
          </span>
        )}
        <span className="badge neutral mono" title={`prompt hash ${ph ?? "—"}`}>
          protocol {pv}
        </span>
        {sandbox === "subprocess_dev_only" && (
          <span className="badge warn" title="Model code ran in the dev-only subprocess fallback, not Docker">
            DEV SANDBOX
          </span>
        )}
        {sandbox === "docker" && <span className="badge neutral">docker sandbox</span>}
        <span className="badge neutral mono" title="model id">
          {model}
        </span>
      </div>
      <div className="stats">
        <div>
          <span className="k">elapsed</span>
          <span className="v mono">{fmtDuration(p.elapsed)}</span>
        </div>
        <div title="sum of cost_usd over model_call events shown">
          <span className="k">est. cost</span>
          <span className="v mono">
            {fmtUsd(p.cost)} <span className="muted">/ {p.nCalls} calls</span>
          </span>
        </div>
        {p.health && !p.health.docker_available && (
          <div title="docker info did not answer">
            <span className="k">docker</span>
            <span className="v warn-text">unavailable</span>
          </div>
        )}
      </div>
    </header>
  );
}
