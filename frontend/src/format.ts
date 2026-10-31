export const fmtNum = (v: unknown, digits = 3): string => {
  if (v === null || v === undefined || v === "") return "—";
  const n = Number(v);
  if (!Number.isFinite(n)) return "—";
  return n.toFixed(digits);
};

export const fmtPct = (v: unknown, digits = 0): string => {
  const n = Number(v);
  if (v === null || v === undefined || !Number.isFinite(n)) return "—";
  return `${(n * 100).toFixed(digits)}%`;
};

export const fmtUsd = (v: number): string => (v < 0.01 && v > 0 ? `$${v.toFixed(4)}` : `$${v.toFixed(2)}`);

export const fmtRel = (s: number): string => {
  if (!Number.isFinite(s)) return "—";
  const sign = s < 0 ? "-" : "";
  s = Math.abs(s);
  const m = Math.floor(s / 60);
  const sec = s - m * 60;
  return `${sign}${String(m).padStart(2, "0")}:${sec.toFixed(1).padStart(4, "0")}`;
};

export const fmtDuration = (s: number): string => {
  if (!Number.isFinite(s) || s < 0) return "—";
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  const sec = Math.floor(s % 60);
  return h ? `${h}h ${m}m ${sec}s` : m ? `${m}m ${sec}s` : `${sec}s`;
};

export const fmtDate = (ts: number | null | undefined): string =>
  ts ? new Date(ts * 1000).toLocaleString(undefined, { dateStyle: "medium", timeStyle: "medium" }) : "—";

export const short = (s: string | null | undefined, n = 12): string => (s ? s.slice(0, n) : "—");

/** Stride downsample that always keeps flagged points (e.g. overrides) and the last point. */
export function downsample<T>(xs: T[], max: number, keep?: (x: T) => boolean): T[] {
  if (xs.length <= max) return xs;
  const stride = Math.ceil(xs.length / max);
  const out: T[] = [];
  xs.forEach((x, i) => {
    if (i % stride === 0 || i === xs.length - 1 || (keep && keep(x))) out.push(x);
  });
  return out;
}
