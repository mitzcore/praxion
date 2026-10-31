import { useEffect, useRef, useState } from "react";
import { api, type Health, type RunDetail } from "../api";
import type { Mode } from "../App";

interface Props {
  health: Health | null;
  run: RunDetail | null;
  stage: string;
  mode: Mode;
  selected: string | null;
  onStarted: (id: string) => void;
  onAction: () => void;
  onError: (e: string) => void;
  startReplay: (speed: number) => void;
  changeReplaySpeed: (speed: number) => void;
  exitReplay: () => void;
}

const DEFAULT_FAMILIES = ["actuator_lag", "pump_derate", "extra_leak", "drain_shift"];

export default function Controls(p: Props) {
  const [formOpen, setFormOpen] = useState(false);
  const [menuOpen, setMenuOpen] = useState(false);
  const [speed, setSpeed] = useState(p.mode.kind === "replay" ? p.mode.speed : 4);
  const [pending, setPending] = useState<string | null>(null);
  const menuRef = useRef<HTMLDivElement>(null);
  const replay = p.mode.kind === "replay";
  const proc = p.run?.process ?? null;
  const busyElsewhere = p.health?.busy_run && p.health.busy_run !== p.selected ? p.health.busy_run : null;

  useEffect(() => {
    const close = (e: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) setMenuOpen(false);
    };
    document.addEventListener("mousedown", close);
    return () => document.removeEventListener("mousedown", close);
  }, []);

  let disturbWhy: string | null = null;
  if (replay) disturbWhy = "Replay shows a recorded run; nothing can be changed.";
  else if (!p.selected) disturbWhy = "Select a run.";
  else if (p.stage !== "DEPLOYABLE") disturbWhy = `Needs stage DEPLOYABLE (an approved controller); run is ${p.stage}.`;
  else if (!proc?.in_process)
    disturbWhy = "Run was recorded by another process; monitoring needs its live trusted session.";
  else if (proc.busy) disturbWhy = "Run is still executing.";

  const stopWhy = replay ? "Replay is read-only." : !proc?.busy ? "Run is not executing in this server." : null;

  const disturb = async (family: string) => {
    if (!p.selected) return;
    setMenuOpen(false);
    setPending("disturbance");
    try {
      await api.disturb(p.selected, family);
      p.onAction();
    } catch (e: any) {
      p.onError(`disturbance: ${e.message}`);
    } finally {
      setPending(null);
    }
  };

  const stop = async () => {
    if (!p.selected) return;
    setPending("stop");
    try {
      await api.stop(p.selected);
      p.onAction();
    } catch (e: any) {
      p.onError(`stop: ${e.message}`);
    } finally {
      setPending(null);
    }
  };

  return (
    <div className="controls">
      <button className="primary" onClick={() => setFormOpen((v) => !v)} disabled={!!busyElsewhere || replay}
        title={busyElsewhere ? `Run ${busyElsewhere} is executing; one run at a time` : replay ? "Exit replay first" : ""}>
        Start Discovery
      </button>
      <div className="menu" ref={menuRef}>
        <button onClick={() => setMenuOpen((v) => !v)} disabled={!!disturbWhy || pending === "disturbance"}
          title={disturbWhy ?? "Inject a hidden plant change. The agent is not told which."}>
          Introduce Disturbance ▾
        </button>
        {menuOpen && !disturbWhy && (
          <div className="menu-list" role="menu">
            {(p.health?.families ?? DEFAULT_FAMILIES).map((f) => (
              <button key={f} role="menuitem" className="ghost" onClick={() => disturb(f)}>
                {f}
              </button>
            ))}
            <div className="muted small pad">Operator-only. Events never record the family.</div>
          </div>
        )}
      </div>
      <button onClick={stop} disabled={!!stopWhy || pending === "stop"} title={stopWhy ?? "Stop at next budget check"}>
        {proc?.stop_requested ? "Stop requested…" : "Stop"}
      </button>
      <a className={`button ${p.selected ? "" : "disabled"}`} href={p.selected ? api.exportUrl(p.selected) : undefined}
        download>
        Export Evidence
      </a>
      <div className="replay-ctl">
        <select value={replay && p.mode.kind === "replay" ? p.mode.speed : speed} aria-label="Replay speed"
          title={replay ? "Changes speed in place (resumes after the last shown event)" : "Replay speed"}
          onChange={(e) => {
            const v = Number(e.target.value);
            setSpeed(v);
            if (replay) p.changeReplaySpeed(v);
          }}>
          {[1, 4, 16].map((s) => (
            <option key={s} value={s}>
              {s}x
            </option>
          ))}
        </select>
        <button onClick={() => p.startReplay(speed)} disabled={!p.selected}>
          {replay ? "Restart Replay" : "Replay"}
        </button>
        {replay && (
          <button className="ghost" onClick={p.exitReplay}>
            Exit replay{p.mode.kind === "replay" && p.mode.done ? " (finished)" : ""}
          </button>
        )}
      </div>
      {disturbWhy && !replay && <span className="hint">Disturbance: {disturbWhy}</span>}
      {proc?.error && <span className="hint bad-text">run crashed: {proc.error}</span>}
      {formOpen && (
        <StartForm health={p.health} onClose={() => setFormOpen(false)} onStarted={(id) => {
          setFormOpen(false);
          p.onStarted(id);
        }} onError={p.onError} />
      )}
    </div>
  );
}

function StartForm(p: {
  health: Health | null;
  onClose: () => void;
  onStarted: (id: string) => void;
  onError: (e: string) => void;
}) {
  const [f, setF] = useState({
    label: "run",
    agent_mode: "live",
    model: p.health?.model_default ?? "",
    plant_seed: 7,
    sandbox_mode: p.health?.sandbox_mode === "subprocess_dev_only" ? "subprocess_dev_only" : "docker",
    max_experiments: 12,
    max_candidates: 5,
  });
  const [submitting, setSubmitting] = useState(false);
  const set = (k: string, v: any) => setF((x) => ({ ...x, [k]: v }));
  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setSubmitting(true);
    try {
      const body = { ...f, model: f.model || null };
      const r = await api.start(body);
      p.onStarted(r.run_id);
    } catch (err: any) {
      p.onError(`start: ${err.message}`);
    } finally {
      setSubmitting(false);
    }
  };
  return (
    <form className="start-form" onSubmit={submit}>
      <label>
        label
        <input value={f.label} pattern="[A-Za-z0-9_]{1,40}" onChange={(e) => set("label", e.target.value)} />
      </label>
      <label>
        agent
        <select value={f.agent_mode} onChange={(e) => set("agent_mode", e.target.value)}>
          <option value="live">live (Muse)</option>
          <option value="mock">mock (CI plumbing)</option>
        </select>
      </label>
      <label>
        model
        <select value={f.model} onChange={(e) => set("model", e.target.value)} disabled={f.agent_mode === "mock"}>
          {["muse-wonder-1.0", "muse-spark-1.3"].map((m) => (
            <option key={m} value={m}>
              {m}
            </option>
          ))}
        </select>
      </label>
      <label>
        plant seed
        <input type="number" min={0} value={f.plant_seed} onChange={(e) => set("plant_seed", Number(e.target.value))} />
      </label>
      <label>
        sandbox
        <select value={f.sandbox_mode} onChange={(e) => set("sandbox_mode", e.target.value)}>
          <option value="docker">docker{p.health && !p.health.docker_available ? " (unavailable)" : ""}</option>
          <option value="subprocess_dev_only">subprocess (dev only)</option>
        </select>
      </label>
      <label>
        max experiments
        <input type="number" min={1} max={40} value={f.max_experiments}
          onChange={(e) => set("max_experiments", Number(e.target.value))} />
      </label>
      <label>
        max candidates
        <input type="number" min={1} max={10} value={f.max_candidates}
          onChange={(e) => set("max_candidates", Number(e.target.value))} />
      </label>
      <div className="form-actions">
        <button type="submit" className="primary" disabled={submitting}>
          {submitting ? "Starting…" : "Start"}
        </button>
        <button type="button" className="ghost" onClick={p.onClose}>
          Cancel
        </button>
      </div>
    </form>
  );
}
