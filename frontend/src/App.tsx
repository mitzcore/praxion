import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  api,
  type ControllerInfo,
  type Evaluations,
  type BoardVerification,
  type ExperimentFacts,
  type Health,
  type RunDetail,
  type RunEvent,
  type RunListing,
  TANK_DISPLAY,
} from "./api";
import Header from "./components/Header";
import Controls from "./components/Controls";
import PlantPanel from "./components/PlantPanel";
import TimelinePanel from "./components/TimelinePanel";
import CodePanel from "./components/CodePanel";
import EvidencePanel from "./components/EvidencePanel";

export type Mode = { kind: "normal" } | { kind: "replay"; speed: number; nonce: number; done: boolean };

const REFRESH_KINDS = new Set([
  "stage",
  "candidate_registered",
  "static_check",
  "sandbox_check",
  "evaluation",
  "candidate_approved",
  "candidate_failed_gate",
  "monitoring_result",
  "adaptation_result",
  "error",
]);

function readUrl(): { run: string | null; replay: boolean; speed: number } {
  const p = new URLSearchParams(window.location.search);
  return { run: p.get("run"), replay: p.get("replay") === "1", speed: Number(p.get("speed") || 1) || 1 };
}

function writeUrl(run: string | null, mode: Mode) {
  const p = new URLSearchParams();
  if (run) p.set("run", run);
  if (mode.kind === "replay") {
    p.set("replay", "1");
    p.set("speed", String(mode.speed));
  }
  const q = p.toString();
  window.history.replaceState(null, "", q ? `?${q}` : window.location.pathname);
}

export default function App() {
  const initial = useRef(readUrl());
  const [health, setHealth] = useState<Health | null>(null);
  const [runs, setRuns] = useState<RunListing[]>([]);
  const [selected, setSelected] = useState<string | null>(initial.current.run);
  const [mode, setMode] = useState<Mode>(
    initial.current.replay ? { kind: "replay", speed: initial.current.speed, nonce: 1, done: false } : { kind: "normal" },
  );
  const [events, setEvents] = useState<RunEvent[]>([]);
  const [run, setRun] = useState<RunDetail | null>(null);
  const [controllers, setControllers] = useState<ControllerInfo[]>([]);
  const [evals, setEvals] = useState<Evaluations | null>(null);
  const [expFacts, setExpFacts] = useState<ExperimentFacts[]>([]);
  const [board, setBoard] = useState<BoardVerification | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [now, setNow] = useState(Date.now() / 1000);

  const refreshRuns = useCallback(() => api.runs().then(setRuns).catch((e) => setError(String(e.message || e))), []);

  useEffect(() => {
    api.health().then(setHealth).catch((e) => setError(`health: ${e.message}`));
    refreshRuns();
    if (!initial.current.run) {
      api
        .config()
        .then((c) => {
          if (c.replay_run) {
            setSelected(c.replay_run);
            setMode({ kind: "replay", speed: c.replay_speed || 1, nonce: Date.now(), done: false });
          }
        })
        .catch(() => undefined);
    }
  }, [refreshRuns]);

  // Default selection: most recent run.
  useEffect(() => {
    if (!selected && runs.length) setSelected(runs[0].id);
  }, [runs, selected]);

  useEffect(() => writeUrl(selected, mode), [selected, mode]);

  // Artifact fetches (debounced on relevant events).
  const refreshTimer = useRef<number | null>(null);
  const refreshArtifacts = useCallback(
    (id: string) => {
      if (refreshTimer.current) window.clearTimeout(refreshTimer.current);
      refreshTimer.current = window.setTimeout(() => {
        api.run(id).then(setRun).catch((e) => setError(`run: ${e.message}`));
        api.controllers(id).then(setControllers).catch((e) => setError(`controllers: ${e.message}`));
        api.evaluations(id).then(setEvals).catch((e) => setError(`evaluations: ${e.message}`));
        api.experiments(id).then(setExpFacts).catch(() => setExpFacts([]));
        api.boardVerification(id).then(setBoard).catch(() => setBoard(null));
      }, 400);
    },
    [],
  );

  // Speed is deliberately not part of the key: changing it reconnects with after=<last seq> and
  // keeps the rendered state (see changeReplaySpeed).
  const modeKey = mode.kind === "replay" ? `replay:${mode.nonce}` : "normal";
  const lastSeqRef = useRef(0);
  const reconnectRef = useRef<((speed: number) => void) | null>(null);
  const initialSpeedRef = useRef(mode.kind === "replay" ? mode.speed : 1);
  initialSpeedRef.current = mode.kind === "replay" ? mode.speed : initialSpeedRef.current;

  // Event source: full history + live tail, or paced replay.
  useEffect(() => {
    if (!selected) return;
    const id = selected;
    let closed = false;
    let es: EventSource | null = null;
    setEvents([]);
    setRun(null);
    setControllers([]);
    setEvals(null);
    setExpFacts([]);
    setBoard(null);
    setError(null);
    refreshArtifacts(id);

    const attach = (url: string, replay: boolean) => {
      es = new EventSource(url);
      es.addEventListener("event", (m) => {
        const rec = JSON.parse((m as MessageEvent).data) as RunEvent;
        lastSeqRef.current = Math.max(lastSeqRef.current, rec.seq);
        setEvents((prev) => (prev.length && prev[prev.length - 1].seq >= rec.seq ? prev : [...prev, rec]));
        if (!replay && rec.kind === "experiment_result") api.experiments(id).then(setExpFacts).catch(() => undefined);
        if (!replay && REFRESH_KINDS.has(rec.kind)) {
          refreshArtifacts(id);
          if (rec.kind === "stage") refreshRuns();
        }
      });
      es.addEventListener("end", () => {
        es?.close();
        if (replay) setMode((m) => (m.kind === "replay" ? { ...m, done: true } : m));
        else refreshArtifacts(id);
      });
      es.onerror = () => {
        if (closed) es?.close();
      };
    };

    lastSeqRef.current = 0;
    if (mode.kind === "replay") {
      attach(api.streamUrl(id, { replay: true, speed: initialSpeedRef.current }), true);
      reconnectRef.current = (speed: number) => {
        es?.close();
        attach(api.streamUrl(id, { replay: true, speed, after: lastSeqRef.current }), true);
      };
    } else {
      reconnectRef.current = null;
      api
        .events(id)
        .then((evs) => {
          if (closed) return;
          setEvents(evs);
          const last = evs.length ? evs[evs.length - 1].seq : 0;
          attach(api.streamUrl(id, { after: last }), false);
        })
        .catch((e) => setError(`events: ${e.message}`));
    }
    return () => {
      closed = true;
      reconnectRef.current = null;
      es?.close();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selected, modeKey, refreshArtifacts, refreshRuns]);

  const busy = !!run?.process?.busy;
  useEffect(() => {
    if (!busy) return;
    const t = window.setInterval(() => setNow(Date.now() / 1000), 1000);
    const p = window.setInterval(() => selected && api.run(selected).then(setRun).catch(() => undefined), 5000);
    return () => {
      window.clearInterval(t);
      window.clearInterval(p);
    };
  }, [busy, selected]);

  // ---------- gating: only artifacts whose producing event has been seen are shown
  const gated = useMemo(() => {
    const regs = new Set(events.filter((e) => e.kind === "candidate_registered").map((e) => e.candidate_id));
    const evalSeen = new Set(
      events
        .filter((e) => e.kind === "evaluation")
        .map((e) => `${String(e.suite).startsWith("disturbance") ? "disturbance" : "heldout"}:${e.candidate_id}`),
    );
    const adaptSeen = new Set(events.filter((e) => e.kind === "adaptation_result").map((e) => e.candidate_id));
    const monSeen = events.some((e) => e.kind === "monitoring_result");
    const ctrls = controllers.filter((c) => regs.has(c.candidate_id));
    const ev: Evaluations | null = evals
      ? {
          heldout: evals.heldout.filter((f) => evalSeen.has(`heldout:${f.data.candidate_id}`)),
          disturbance: evals.disturbance.filter((f) => evalSeen.has(`disturbance:${f.data.candidate_id}`)),
          adaptation: evals.adaptation.filter((f) =>
            [...adaptSeen].some((cid) => String(cid).endsWith(`-v${f.version}`)),
          ),
          monitoring: monSeen ? evals.monitoring : null,
          repair_verdicts: evals.repair_verdicts.filter((v) => adaptSeen.has(v.candidate_id)),
          protocol: evals.protocol,
          twin_fit: events.some((e) => e.kind === "twin_fitted") ? evals.twin_fit : null,
          twin_fit_after_change: events.some((e) => e.kind === "changed_twin_fitted") ? evals.twin_fit_after_change : null,
        }
      : null;
    // board_verification.json is written after the hardware run: in replay it appears once its
    // board_verification event has been replayed (or, for bundles without that event, when the replay ends).
    const boardSeen =
      mode.kind === "normal" || events.some((e) => e.kind === "board_verification") || (mode.kind === "replay" && mode.done);
    return { ctrls, ev, board: boardSeen ? board : null };
  }, [events, controllers, evals, board, mode]);

  const stage = useMemo(() => {
    for (let i = events.length - 1; i >= 0; i--) if (events[i].kind === "stage") return events[i].to as string;
    return events.length ? "NEW" : run?.stage ?? "—";
  }, [events, run]);

  const t0 = events.length ? events[0].ts : run?.started_at ?? null;
  const lastTs = events.length ? events[events.length - 1].ts : null;
  const elapsed = t0 == null ? NaN : (mode.kind === "normal" && busy ? now : lastTs ?? t0) - t0;
  const cost = events.filter((e) => e.kind === "model_call").reduce((a, e) => a + Number(e.cost_usd || 0), 0);
  const nCalls = events.filter((e) => e.kind === "model_call").length;
  const runStarted = events.find((e) => e.kind === "run_started");

  const profile = run?.display_profile ?? TANK_DISPLAY;
  const startReplay = (speed: number) => setMode({ kind: "replay", speed, nonce: Date.now(), done: false });
  const exitReplay = () => setMode({ kind: "normal" });
  const changeReplaySpeed = (speed: number) => {
    if (mode.kind !== "replay" || mode.speed === speed) return;
    setMode({ ...mode, speed });
    if (!mode.done) reconnectRef.current?.(speed);
  };

  return (
    <div className="app">
      <Header
        runs={runs}
        selected={selected}
        onSelect={(id) => {
          setSelected(id);
          setMode({ kind: "normal" });
        }}
        mode={mode}
        run={run}
        runStarted={runStarted}
        health={health}
        stage={stage}
        elapsed={elapsed}
        cost={cost}
        nCalls={nCalls}
        recordedAt={t0}
        profile={run?.display_profile ?? null}
      />
      <Controls
        health={health}
        run={run}
        stage={stage}
        mode={mode}
        selected={selected}
        onStarted={(id) => {
          refreshRuns().then(() => {
            setSelected(id);
            setMode({ kind: "normal" });
          });
        }}
        onAction={() => selected && refreshArtifacts(selected)}
        onError={setError}
        startReplay={startReplay}
        changeReplaySpeed={changeReplaySpeed}
        exitReplay={exitReplay}
      />
      {error && (
        <div className="banner" role="alert">
          <span>{error}</span>
          <button className="ghost" onClick={() => setError(null)}>
            dismiss
          </button>
        </div>
      )}
      {!selected ? (
        <div className="empty-state">No runs under the artifact root yet. Start Discovery to record one.</div>
      ) : (
        <main className="grid">
          <PlantPanel profile={profile} events={events} monitoring={gated.ev?.monitoring ?? null} replay={mode.kind === "replay"} />
          <TimelinePanel events={events} facts={expFacts} profile={profile} />
          <CodePanel controllers={gated.ctrls} />
          <EvidencePanel profile={profile} evals={gated.ev} run={run} stage={stage} events={events} board={gated.board} />
        </main>
      )}
      <footer className="foot">
        Every value on this page is read from <code>artifacts/runs/{selected ?? "…"}</code> through the API. Simulation
        results do not establish real-world safety.
      </footer>
    </div>
  );
}
