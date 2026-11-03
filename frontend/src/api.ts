// Typed access to the evidence API. Every value the UI renders comes through here.

export type Json = Record<string, any>;

export interface RunEvent {
  seq: number;
  ts: number;
  run_id: string;
  kind: string;
  stage?: string;
  replay?: boolean;
  [k: string]: any;
}

export interface RunListing {
  id: string;
  label: string;
  stage: string;
  model_id: string | null;
  agent_mode: string | null;
  started: number | null;
  last_event_at: number | null;
  n_candidates: number;
  has_result: boolean;
  active: boolean;
}

export interface Health {
  status: string;
  sandbox_mode: string;
  docker_available: boolean;
  agent_mode_default: string;
  model_default: string;
  prompt_version: string;
  prompt_hash: string;
  families: string[];
  busy_run: string | null;
}

export interface ProcessStatus {
  in_process: boolean;
  busy: boolean;
  phase: string;
  stage: string;
  stop_requested: boolean;
  error: string | null;
}

export interface RunDetail extends Json {
  run_id: string;
  stage: string;
  stage_from_events?: string;
  source: "result.json" | "event_log";
  model_id: string | null;
  agent_mode: string | null;
  prompt_version: string | null;
  prompt_hash: string | null;
  sandbox_mode: string | null;
  started_at: number | null;
  last_event_at: number | null;
  process: ProcessStatus | null;
  display_profile?: DisplayProfile;
}

export interface ControllerInfo {
  version: number;
  candidate_id: string;
  sha256: string;
  sha256_recorded: string | null;
  sha256_verified: boolean;
  byte_length: number;
  parent_id: string | null;
  parent_version: number | null;
  model_id: string | null;
  prompt_hash: string | null;
  created_at: string | null;
  status: string | null;
  submission_kind: string | null;
  static_ok: boolean | null;
  static_violations: string[] | null;
  sandbox_ok: boolean | null;
  sandbox_detail: string[] | null;
  rationale: string | null;
  predicted_behavior: string | null;
  diagnosis: string | null;
  diagnosis_category: string | null;
  source: string;
  parent_source: string | null;
  machine_card: string | null;
  diff_from_parent: string | null;
}

export interface EvalFile {
  file: string;
  kind: "heldout" | "disturbance" | "adaptation";
  version: number | null;
  data: Json;
}

export interface RecordedOutcome {
  stage: string | null;
  reason: string | null;
  source: string;
  final: boolean;
}

export interface RepairVerdict {
  version: number;
  candidate_id: string;
  gate3_passed: boolean | null;
  gate3_reasons: string[];
  n_improved: number | null;
  median_reduction: number | null;
  nominal_after_repair_passed: boolean | null;
  diagnosis_category: string | null;
  diagnosis_correct: boolean | null;
  recorded_candidate_status: string | null;
  recorded_outcome: RecordedOutcome;
  verdict_disagrees: boolean;
  note: string | null;
}

export interface ExperimentFacts {
  id: string;
  phase: string;
  status: string;
  t_start: number | null;
  command_u: number | null;
  duration_s: number | null;
  command_before: number | null;
  seconds_since_command_last_changed_at_start: number | null;
}

export interface DisplayProfile {
  name: string;
  dt: number;
  target: number;
  band: [number, number];
  y_unit: string;
  y_scale: number;
  y_offset: number;
  eval_plant: "simulator" | "twin" | "custom";
  operator_disturbance: boolean | null;
  soft_high_limit: number;
  hard_cutoff: number;
  source: string;
}

export const TANK_DISPLAY: DisplayProfile = {
  name: "tank", dt: 0.1, target: 0.6, band: [0.55, 0.65], y_unit: "level fraction", y_scale: 1, y_offset: 0,
  eval_plant: "simulator", operator_disturbance: false, soft_high_limit: 0.85, hard_cutoff: 0.9, source: "default_tank",
};

export const isCelsius = (p: DisplayProfile) => p.y_unit === "°C";
/** display value = y * y_scale + y_offset */
export const toDisplay = (p: DisplayProfile, y: number | null | undefined): number | null =>
  y == null || !Number.isFinite(Number(y)) ? null : Number(y) * p.y_scale + p.y_offset;
/** a difference/error (e.g. an MAE) in display units: offset does not apply */
export const toDisplayDelta = (p: DisplayProfile, d: number | null | undefined): number | null =>
  d == null || !Number.isFinite(Number(d)) ? null : Number(d) * p.y_scale;
export const fmtY = (p: DisplayProfile, y: number | null | undefined, digits?: number): string => {
  const v = toDisplay(p, y);
  if (v == null) return "—";
  return isCelsius(p) ? `${v.toFixed(digits ?? 1)} °C` : v.toFixed(digits ?? 2);
};
export const profileLabel = (p: DisplayProfile): string =>
  ({ tank: "Tank", tclab_sim: "TCLab (sim)", tclab: "TCLab" } as Record<string, string>)[p.name] ?? p.name;

export interface Evaluations {
  heldout: EvalFile[];
  disturbance: EvalFile[];
  adaptation: EvalFile[];
  monitoring: Json | null;
  repair_verdicts: RepairVerdict[];
  protocol: { prompt_version: string | null; prompt_hash: string | null };
  twin_fit: Json | null;
  twin_fit_after_change: Json | null;
}

// <run_dir>/board_verification.json (backend/evaluation/board_verify.py), shown verbatim.
export interface TraceStep {
  t: number;
  y: number;
  h_true: number;
  u_requested: number;
  u_applied: number;
  override: boolean;
  reason: string;
}

export interface StoredTrace {
  steps: TraceStep[];
  dt: number;
  target: number;
  disturbance_at: number | null;
  meta: Json;
}

export interface BoardTrial {
  label: string;
  controller_sha256: string;
  start_T_display?: number | null;
  trace: StoredTrace;
  post_mae: number | null;
  post_in_band: number | null;
  overrides: number | null;
  hard_violations: number | null;
  invalid_outputs: number | null;
  interlock_hit: boolean | null;
  [k: string]: any;
}

export interface BoardComparison {
  post_mae_v1: number | null;
  post_mae_v2: number | null;
  reduction: number | null;
  in_band_v1: number | null;
  in_band_v2: number | null;
}

export interface PredVsMeas {
  predicted: number | null;
  measured: number | null;
}

export interface BoardVerification {
  trials: BoardTrial[];
  order: string[];
  pre_s: number;
  post_s: number;
  disturbance: { family: string | null; magnitude: number | null; applied_by: "trusted_actuator" | "operator" | string; at_t?: number | null };
  comparison: BoardComparison | Json;
  twin_prediction: { trials: BoardTrial[]; comparison: BoardComparison | Json; prediction_basis?: string | null } | null;
  twin_prediction_reason?: string | null;
  prediction_vs_board: { post_mae_v1?: PredVsMeas; post_mae_v2?: PredVsMeas; reduction?: PredVsMeas; direction_agrees?: boolean; [k: string]: any } | null;
  prediction_basis?: string | null;
  fake_board?: boolean;
  [k: string]: any;
}

export const CHANGED_MACHINE_SUITE = "disturbance:changed_machine";
export const suiteLabel = (suite: string | null | undefined): string =>
  suite === CHANGED_MACHINE_SUITE ? "changed-machine twin (refitted from after-change experiments)" : suite ?? "—";

async function j<T>(url: string, init?: RequestInit): Promise<T> {
  const r = await fetch(url, init);
  if (!r.ok) {
    let detail = `${r.status} ${r.statusText}`;
    try {
      const b = await r.json();
      if (b?.detail) detail = typeof b.detail === "string" ? b.detail : JSON.stringify(b.detail);
    } catch {
      /* not JSON */
    }
    throw new Error(detail);
  }
  return r.json() as Promise<T>;
}

const enc = encodeURIComponent;

export const api = {
  health: () => j<Health>("/health"),
  config: () => j<{ replay_run: string | null; replay_speed: number }>("/api/config"),
  runs: () => j<RunListing[]>("/api/runs"),
  run: (id: string) => j<RunDetail>(`/api/runs/${enc(id)}`),
  events: (id: string, after = 0) => j<RunEvent[]>(`/api/runs/${enc(id)}/events?after=${after}`),
  controllers: (id: string) => j<ControllerInfo[]>(`/api/runs/${enc(id)}/controllers`),
  experiments: (id: string) => j<ExperimentFacts[]>(`/api/runs/${enc(id)}/experiments`),
  evaluations: (id: string) => j<Evaluations>(`/api/runs/${enc(id)}/evaluations?traces=disturbance`),
  boardVerification: (id: string) => j<BoardVerification | null>(`/api/runs/${enc(id)}/board_verification`),
  start: (body: Json) =>
    j<{ run_id: string }>("/api/runs", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }),
  disturb: (id: string, family: string) =>
    j<{ accepted: boolean }>(`/api/runs/${enc(id)}/disturbance`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ family }),
    }),
  stop: (id: string) => j<Json>(`/api/runs/${enc(id)}/stop`, { method: "POST" }),
  exportUrl: (id: string) => `/api/runs/${enc(id)}/export`,
  streamUrl: (id: string, opts: { replay?: boolean; speed?: number; after?: number }) => {
    const p = new URLSearchParams();
    if (opts.replay) p.set("replay", "1");
    if (opts.speed) p.set("speed", String(opts.speed));
    if (opts.after) p.set("after", String(opts.after));
    return `/api/runs/${enc(id)}/stream?${p.toString()}`;
  },
};
