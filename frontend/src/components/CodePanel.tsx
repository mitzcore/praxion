import { useEffect, useMemo, useState } from "react";
import { diffLines } from "diff";
import type { ControllerInfo } from "../api";
import { short } from "../format";

type Row = { l?: string; r?: string; ln?: number; rn?: number; kind: "same" | "del" | "add" | "chg" };

function sideBySide(a: string, b: string): Row[] {
  const rows: Row[] = [];
  let ln = 1;
  let rn = 1;
  const parts = diffLines(a, b);
  const split = (v: string) => {
    const xs = v.split("\n");
    if (xs.length && xs[xs.length - 1] === "") xs.pop();
    return xs;
  };
  for (let i = 0; i < parts.length; i++) {
    const p = parts[i];
    if (!p.added && !p.removed) {
      for (const x of split(p.value)) rows.push({ l: x, r: x, ln: ln++, rn: rn++, kind: "same" });
    } else if (p.removed && parts[i + 1]?.added) {
      const del = split(p.value);
      const add = split(parts[i + 1].value);
      const n = Math.max(del.length, add.length);
      for (let k = 0; k < n; k++) {
        const l = del[k];
        const r = add[k];
        rows.push({ l, r, ln: l !== undefined ? ln++ : undefined, rn: r !== undefined ? rn++ : undefined,
          kind: l !== undefined && r !== undefined ? "chg" : l !== undefined ? "del" : "add" });
      }
      i++;
    } else if (p.removed) {
      for (const x of split(p.value)) rows.push({ l: x, ln: ln++, kind: "del" });
    } else {
      for (const x of split(p.value)) rows.push({ r: x, rn: rn++, kind: "add" });
    }
  }
  return rows;
}

const statusTone = (s: string | null) =>
  s === "approved" ? "good" : s?.startsWith("rejected") || s === "failed_gate" ? "bad" : "info";

export default function CodePanel({ controllers }: { controllers: ControllerInfo[] }) {
  const [ver, setVer] = useState<number | null>(null);
  useEffect(() => {
    if (!controllers.length) setVer(null);
    else if (ver == null || !controllers.some((c) => c.version === ver)) setVer(controllers[controllers.length - 1].version);
  }, [controllers, ver]);
  const c = controllers.find((x) => x.version === ver) ?? null;
  const rows = useMemo(() => (c?.parent_source != null ? sideBySide(c.parent_source, c.source) : null), [c]);
  const stats = useMemo(() => {
    if (!rows) return null;
    return {
      add: rows.filter((r) => r.kind === "add" || r.kind === "chg").length,
      del: rows.filter((r) => r.kind === "del" || r.kind === "chg").length,
    };
  }, [rows]);

  return (
    <section className="panel code">
      <div className="panel-head">
        <h2>Controller code</h2>
        <div className="tabs" role="tablist">
          {controllers.map((x) => (
            <button key={x.version} role="tab" aria-selected={x.version === ver}
              className={`tab ${x.version === ver ? "active" : ""}`} onClick={() => setVer(x.version)}>
              v{x.version}
              <span className={`dot ${statusTone(x.status)}`} />
            </button>
          ))}
        </div>
      </div>
      {!c ? (
        <div className="empty">No controller registered yet.</div>
      ) : (
        <>
          <dl className="meta">
            <div>
              <dt>sha256</dt>
              <dd className="mono" title={c.sha256}>
                {short(c.sha256, 16)}{" "}
                {c.sha256_verified ? (
                  <span className="good-text small" title="file bytes hash to the registry's recorded sha256">verified</span>
                ) : (
                  <span className="bad-text small">MISMATCH vs registry {short(c.sha256_recorded, 12)}</span>
                )}
              </dd>
            </div>
            <div>
              <dt>model</dt>
              <dd className="mono">{c.model_id ?? "—"}</dd>
            </div>
            <div>
              <dt>prompt hash</dt>
              <dd className="mono">{c.prompt_hash ?? "—"}</dd>
            </div>
            <div>
              <dt>status</dt>
              <dd>
                <span className={`chip ${statusTone(c.status)}`}>{c.status ?? "—"}</span>
              </dd>
            </div>
            <div>
              <dt>kind</dt>
              <dd>{c.submission_kind ?? "—"}</dd>
            </div>
            <div>
              <dt>static / sandbox</dt>
              <dd>
                {c.static_ok == null ? "—" : c.static_ok ? "pass" : "fail"} / {c.sandbox_ok == null ? "—" : c.sandbox_ok ? "pass" : "fail"}
              </dd>
            </div>
            <div>
              <dt>bytes</dt>
              <dd className="mono">{c.byte_length}</dd>
            </div>
            <div>
              <dt>parent</dt>
              <dd className="mono">{c.parent_version != null ? `v${c.parent_version}` : "none"}</dd>
            </div>
          </dl>
          {c.diagnosis_category && (
            <div className="note">
              <b>Muse diagnosis ({c.diagnosis_category}):</b> {c.diagnosis}
            </div>
          )}
          <div className="code-wrap">
            {rows ? (
              <>
                <div className="diff-head mono small">
                  <span>v{c.parent_version} (parent)</span>
                  <span>
                    v{c.version} · <span className="good-text">+{stats?.add}</span> <span className="bad-text">−{stats?.del}</span>
                  </span>
                </div>
                <table className="diff mono">
                  <tbody>
                    {rows.map((r, i) => (
                      <tr key={i} className={r.kind}>
                        <td className="n">{r.ln ?? ""}</td>
                        <td className={`c ${r.kind === "del" || r.kind === "chg" ? "del" : ""}`}>{r.l ?? ""}</td>
                        <td className="n">{r.rn ?? ""}</td>
                        <td className={`c ${r.kind === "add" || r.kind === "chg" ? "add" : ""}`}>{r.r ?? ""}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </>
            ) : (
              <>
                <div className="diff-head mono small">
                  <span>controller_v{c.version}.py · no parent version (first authored controller), shown verbatim</span>
                </div>
                <table className="diff mono single">
                  <tbody>
                    {c.source.split("\n").map((l, i) => (
                      <tr key={i}>
                        <td className="n">{i + 1}</td>
                        <td className="c">{l}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </>
            )}
          </div>
          <div className="cards">
            <div>
              <h3>Machine card (Muse's words)</h3>
              <p className="prose">{c.machine_card ?? "—"}</p>
            </div>
            {c.rationale && (
              <details>
                <summary>design rationale</summary>
                <p className="prose">{c.rationale}</p>
              </details>
            )}
            {c.predicted_behavior && (
              <details>
                <summary>predicted behavior</summary>
                <p className="prose">{c.predicted_behavior}</p>
              </details>
            )}
            {(c.sandbox_detail?.length || c.static_violations?.length) ? (
              <details>
                <summary>static / sandbox detail</summary>
                <ul className="small mono">
                  {(c.static_violations ?? []).map((v, i) => <li key={`s${i}`}>static: {v}</li>)}
                  {(c.sandbox_detail ?? []).map((v, i) => <li key={`b${i}`}>{v}</li>)}
                </ul>
              </details>
            ) : null}
          </div>
        </>
      )}
    </section>
  );
}
