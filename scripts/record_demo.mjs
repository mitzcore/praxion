// Praxion demo recorder: drives the real dashboard in headless Chromium and records video.
//
// Normally launched by scripts/record_demo.py (which starts the API on a free port and runs the
// audit). Direct use:
//   node scripts/record_demo.mjs --base http://127.0.0.1:8000 --run <run_id> --out <dir> \
//        [--audit <audit_stdout.txt>] [--speed-a 4] [--speed-b 16] [--segments default]
//
// Rules: the recorder only navigates, scrolls, selects the replay speed, clicks Replay/Restart and
// controller tabs. It never writes into the dashboard DOM. The one non-dashboard page is the audit
// render, which shows the captured stdout of scripts/audit_run.py verbatim (HTML-escaped).
import { createRequire } from "node:module";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const require = createRequire(path.join(ROOT, "frontend", "package.json"));
const { chromium } = require("playwright");

// ---------------------------------------------------------------- args
function parseArgs(argv) {
  const a = { speedA: 4, speedB: 16, segments: "default", audit: null, headful: false };
  for (let i = 2; i < argv.length; i++) {
    const k = argv[i];
    const v = () => argv[++i];
    if (k === "--base") a.base = v();
    else if (k === "--run") a.run = v();
    else if (k === "--out") a.out = v();
    else if (k === "--audit") a.audit = v();
    else if (k === "--speed-a") a.speedA = Number(v());
    else if (k === "--speed-b") a.speedB = Number(v());
    else if (k === "--segments") a.segments = v();
    else if (k === "--speed-note") a.speedNote = v();
    else if (k === "--audit-cmd") a.auditCmd = v();
    else if (k === "--headful") a.headful = true;
    else throw new Error(`unknown arg ${k}`);
  }
  for (const k of ["base", "run", "out"]) if (!a[k]) throw new Error(`--${k} is required`);
  if (a.segments !== "default") throw new Error(`unknown segment plan '${a.segments}' (only 'default')`);
  return a;
}
const args = parseArgs(process.argv);
fs.mkdirSync(args.out, { recursive: true });
const VIDEO_TMP = path.join(args.out, ".video_tmp");
fs.rmSync(VIDEO_TMP, { recursive: true, force: true });

// ---------------------------------------------------------------- segment plan (docs/DEMO_SCRIPT.md)
// script_time/title/expect mirror the script table. `script_numbers` are the spark2 numbers the
// script speaks; they are checked only when recording that run (other runs: [G3 branch], read
// the observed values instead).
const SCRIPT_RUN = "spark2-20261031-004636-3d012e";
const PLAN = {
  intro: { n: 1, script_time: "0:00-0:15", title: "intro", source: "Pass A start",
    expect: "Header: REPLAY badge, model id, prompt hash/protocol. Plant panel empty." },
  discovery: { n: 2, script_time: "0:15-0:50", title: "discovery", source: "Pass A, first experiments",
    expect: "Timeline: E1..E4 proposals with uncertainty and safety argument; ledger confidences changing; plant responding." },
  readiness: { n: 3, script_time: "0:50-1:05", title: "ready-to-generate", source: "Pass A, readiness",
    expect: "Timeline: last experiment, then the ready-to-generate event with Muse's justification." },
  authoring: { n: 4, script_time: "1:05-1:30", title: "authoring-and-g2", source: "Pass B, authoring and G2",
    expect: "Code panel: controller_v1.py bytes, sha256 'verified', model id. Evidence: held-out table, passes, overrides/violations.",
    script_numbers: ["2265", "10/10"] },
  monitoring: { n: 5, script_time: "1:30-1:55", title: "monitoring", source: "Pass B, monitoring",
    expect: "Plant: disturbance marker, level oscillating. Evidence: Trusted monitor degraded at t, window MAE vs threshold.",
    script_numbers: ["155.3", "0.05"] },
  adapting: { n: 6, script_time: "1:55-2:20", title: "adapting-diff", source: "Pass B, adapting [G3 branch]",
    expect: "Code panel: v1 to v2 diff. Muse diagnosis category and text.", script_numbers: ["response_slower"] },
  final: { n: 7, script_time: "2:20-2:40", title: "final-adaptation", source: "Pass B, final state [G3 branch]",
    expect: "Evidence Adaptation: per-version G3 result; final stage.", script_numbers: ["FAILED"] },
  audit: { n: 8, script_time: "2:40-2:50", title: "audit", source: "Terminal",
    expect: "audit_run.py output with RESULT line and check 6 visible." },
  closing: { n: 9, script_time: "2:50-3:00", title: "closing-header", source: "Dashboard header",
    expect: "Header with REPLAY badge." },
};
const segs = {};
for (const [id, p] of Object.entries(PLAN)) {
  segs[id] = { id, ...p, live: null, closeup: null, screenshots: [], observed: {}, issues: [] };
  if (args.run !== SCRIPT_RUN) delete segs[id].script_numbers;
}

// ---------------------------------------------------------------- timing helpers
let T0 = 0; // ms epoch when the page (and so the video) was created
const now = () => +((Date.now() - T0) / 1000).toFixed(2);
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const log = (...m) => console.log(`[${now().toFixed(1).padStart(6)}s]`, ...m);
const markers = [];
function mark(kind, extra = {}) {
  markers.push({ t: now(), kind, ...extra });
}
function liveStart(id) {
  if (!segs[id].live) segs[id].live = { start_s: now(), end_s: null };
}
function liveEnd(id) {
  if (segs[id].live && segs[id].live.end_s == null) segs[id].live.end_s = now();
}

// ---------------------------------------------------------------- page helpers (read-only DOM queries)
let page;
const q = (fn, arg) => page.evaluate(fn, arg);
const countKind = (k) =>
  q((k) => [...document.querySelectorAll(".timeline .ev-kind")].filter((e) => e.textContent === k).length, k);
const stageChip = () => q(() => document.querySelector(".header .badges .chip")?.textContent ?? "");
const replayFinished = () =>
  q(() => [...document.querySelectorAll(".replay-ctl button")].some((b) => b.textContent.includes("(finished)")));
const text = (sel) => q((s) => document.querySelector(s)?.innerText ?? null, sel);

async function waitUntil(label, fn, timeoutMs) {
  const end = Date.now() + timeoutMs;
  while (Date.now() < end) {
    try {
      if (await fn()) return true;
    } catch {
      /* page mid-render */
    }
    await sleep(100);
  }
  log(`timeout waiting for: ${label}`);
  return false;
}

async function scrollTo(target, offset = 8) {
  // target: CSS selector, {h3: "prefix"} inside evidence, or a number (page Y).
  const y = await q(
    ({ target, offset }) => {
      let el = null;
      if (typeof target === "number") return target;
      if (target.h3) el = [...document.querySelectorAll(".evidence h3")].find((h) => h.textContent.startsWith(target.h3));
      else el = document.querySelector(target);
      if (!el) return null;
      return el.getBoundingClientRect().top + window.scrollY - offset;
    },
    { target, offset },
  );
  if (y == null) return false;
  await q((y) => window.scrollTo({ top: Math.max(0, y), behavior: "smooth" }), y);
  await sleep(1100);
  return true;
}

async function ensureFollow() {
  const cb = page.locator(".timeline .follow input[type=checkbox]");
  if ((await cb.count()) && !(await cb.isChecked())) {
    await cb.check();
    log("timeline follow re-enabled");
  }
}

async function clickTab(version) {
  const tab = page.locator(".code .tabs button", { hasText: new RegExp(`^v${version}$`) });
  if (!(await tab.count())) return false;
  await tab.first().click();
  await sleep(400);
  return true;
}

function slug(s) {
  return s.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "");
}
async function shot(id, suffix = "") {
  const s = segs[id];
  const [mm, ss] = s.script_time.split("-")[0].split(":");
  const name = `s${String(s.n).padStart(2, "0")}_${mm}m${ss}s_${slug(s.title)}${suffix ? "_" + slug(suffix) : ""}.png`;
  await page.screenshot({ path: path.join(args.out, name) });
  s.screenshots.push({ file: name, video_t_s: now() });
  log(`screenshot ${name}`);
}

function checkNumbers(id, haystack) {
  const s = segs[id];
  if (!s.script_numbers) return;
  for (const n of s.script_numbers)
    if (!haystack.includes(n)) s.issues.push(`script says '${n}' but it was not found on screen in this segment`);
}

// ---------------------------------------------------------------- main
const browser = await chromium.launch({ headless: !args.headful });
const ctx = await browser.newContext({
  viewport: { width: 1600, height: 1000 },
  deviceScaleFactor: 1,
  colorScheme: "dark",
  recordVideo: { dir: VIDEO_TMP, size: { width: 1600, height: 1000 } },
});
page = await ctx.newPage();
T0 = Date.now();
const pageErrors = [];
page.on("pageerror", (e) => pageErrors.push(String(e)));

const urlA = `${args.base}/?run=${encodeURIComponent(args.run)}&replay=1&speed=${args.speedA}`;
const STEP_TIMEOUT = 15 * 60 * 1000;
let ok;

// ---- Pass A: intro
mark("pass_A_start", { speed: args.speedA, url: urlA });
liveStart("intro");
await page.goto(urlA, { waitUntil: "domcontentloaded" });
await waitUntil("REPLAY badge", async () => !!(await text(".header .badge.replay")), 20000);
await waitUntil("run_started in timeline", async () => (await countKind("run_started")) > 0, 30000);
await ensureFollow();
await sleep(1200);
segs.intro.observed.replay_badge = await text(".header .badge.replay");
segs.intro.observed.header_badges = await text(".header .badges");
segs.intro.observed.plant = await text(".plant .empty");
if (!segs.intro.observed.replay_badge) segs.intro.issues.push("REPLAY badge not visible");
if (!segs.intro.observed.plant) segs.intro.issues.push("plant panel was not empty at intro (first experiment already arrived)");
await shot("intro");

// ---- Pass A: discovery (alternate plant view and ledger view as results arrive)
ok = await waitUntil("first experiment_proposed", async () => (await countKind("experiment_proposed")) > 0, STEP_TIMEOUT);
liveEnd("intro");
liveStart("discovery");
let seenResults = 0;
let shotDone = false;
while (true) {
  if ((await countKind("ready_to_generate")) > 0 || (await countKind("exploration_budget_exhausted")) > 0) break;
  if (await replayFinished()) break;
  const n = await countKind("experiment_result");
  if (n !== seenResults) {
    seenResults = n;
    await ensureFollow();
    // ledger view keeps the Plant panel head (with its REPLAY badge) at the top edge
    if (n % 2 === 0) await scrollTo(".plant", 4);
    else await scrollTo(0);
    if (n >= 4 && !shotDone) {
      await scrollTo(".plant", 4);
      segs.discovery.observed.ledger_head = await text(".timeline .ledger .sub-head");
      await shot("discovery");
      shotDone = true;
    }
  }
  await sleep(150);
}
if (!shotDone) {
  segs.discovery.issues.push(`fewer than 4 experiment results before readiness (${seenResults})`);
  await shot("discovery");
}
segs.discovery.observed.experiments_proposed = await countKind("experiment_proposed");
segs.discovery.observed.experiment_results = await countKind("experiment_result");
segs.discovery.observed.ledger_revisions = await countKind("ledger");
liveEnd("discovery");

// ---- Pass A: readiness
liveStart("readiness");
await scrollTo(0);
ok = await waitUntil("stage GENERATING", async () => (await stageChip()) === "GENERATING", 60000);
if (!ok) segs.readiness.issues.push(`stage chip never showed GENERATING (shows '${await stageChip()}')`);
segs.readiness.observed.ready_event = await q(() => {
  const li = [...document.querySelectorAll(".timeline .ev")].find((e) =>
    e.querySelector(".ev-kind")?.textContent.match(/^(ready_to_generate|exploration_budget_exhausted)$/));
  return li ? li.innerText : null;
});
if (!segs.readiness.observed.ready_event) segs.readiness.issues.push("no ready_to_generate event visible");
await sleep(800);
await shot("readiness");
await sleep(2500);
liveEnd("readiness");

// ---- switch to Pass B: the UI's speed select + Restart Replay (restarts from seq 0)
const optSpeeds = await q(() => [...document.querySelectorAll(".replay-ctl select option")].map((o) => Number(o.value)));
if (optSpeeds.includes(args.speedB)) {
  await page.locator(".replay-ctl select").selectOption(String(args.speedB));
  await sleep(500);
  await page.locator(".replay-ctl button", { hasText: /Replay/ }).first().click();
  mark("pass_B_start", { speed: args.speedB, via: "speed select + Restart Replay" });
} else {
  const urlB = `${args.base}/?run=${encodeURIComponent(args.run)}&replay=1&speed=${args.speedB}`;
  await page.goto(urlB, { waitUntil: "domcontentloaded" });
  mark("pass_B_start", { speed: args.speedB, via: `URL ${urlB} (speed not in the UI select)` });
}
const passBStart = now();
log(`pass B at ${args.speedB}x`);
await scrollTo(0);
await waitUntil("pass B GENERATING", async () => (await stageChip()) === "GENERATING", STEP_TIMEOUT);
const cutEnd = now();
mark("pass_B_rediscovery_end");

// ---- Pass B: authoring + G2
liveStart("authoring");
await waitUntil("candidate v1 registered", async () => (await countKind("candidate_registered")) >= 1, STEP_TIMEOUT);
await scrollTo(".code");
await waitUntil("first evaluation", async () => (await countKind("evaluation")) >= 1, STEP_TIMEOUT);
await scrollTo(".evidence");
await sleep(600);
liveEnd("authoring");

// ---- Pass B: monitoring
const hasMonitoring = await waitUntil("monitoring_result", async () =>
  (await countKind("monitoring_result")) >= 1 || (await replayFinished()), STEP_TIMEOUT);
liveStart("monitoring");
await scrollTo(0);
await sleep(800);
await scrollTo({ h3: "Trusted monitor" });
await sleep(600);
liveEnd("monitoring");

// ---- Pass B: adapting (v2 diff)
const hasV2 = await waitUntil("candidate v2 registered", async () =>
  (await countKind("candidate_registered")) >= 2 || (await replayFinished()), STEP_TIMEOUT);
liveStart("adapting");
if ((await countKind("candidate_registered")) >= 2) {
  await scrollTo(".code");
  await clickTab(2);
} else segs.adapting.issues.push("no v2 registered during the replay");
liveEnd("adapting");

// ---- Pass B: final
await waitUntil("replay finished", replayFinished, STEP_TIMEOUT);
liveStart("final");
await ensureFollow();
await scrollTo({ h3: "Repair candidate" }) || (await scrollTo(".evidence"));
await sleep(1500);
liveEnd("final");
mark("pass_B_end");
const passBEnd = now();

// ---- close-ups on the final state (panels stay on the final state after the pass ends)
mark("closeups_start");
// 4 authoring
segs.authoring.closeup = { start_s: now(), end_s: null };
await scrollTo(".code");
if (!(await clickTab(1))) segs.authoring.issues.push("no v1 tab");
await sleep(3500);
segs.authoring.observed.code_meta = await text(".code .meta");
await shot("authoring", "code-v1");
await scrollTo({ h3: "Held-out suite" });
await sleep(3500);
segs.authoring.observed.heldout = await q(() => {
  const h = [...document.querySelectorAll(".evidence h3")].find((x) => x.textContent.startsWith("Held-out"));
  return h ? h.closest(".metric-block")?.innerText ?? h.parentElement.innerText : null;
});
if (!segs.authoring.observed.heldout) segs.authoring.issues.push("held-out table not shown");
await shot("authoring", "heldout");
segs.authoring.closeup.end_s = now();
checkNumbers("authoring", `${segs.authoring.observed.code_meta}\n${segs.authoring.observed.heldout}`);

// 5 monitoring
segs.monitoring.closeup = { start_s: now(), end_s: null };
await scrollTo(0);
await sleep(3000);
await shot("monitoring", "plant");
if (await scrollTo({ h3: "Trusted monitor" }, 40)) {
  await sleep(3500);
  segs.monitoring.observed.monitor = await q(() => {
    const h = [...document.querySelectorAll(".evidence h3")].find((x) => x.textContent === "Trusted monitor");
    return h?.parentElement?.innerText ?? null;
  });
  await shot("monitoring", "monitor");
} else segs.monitoring.issues.push("Trusted monitor block not shown (no monitoring_result)");
segs.monitoring.closeup.end_s = now();
checkNumbers("monitoring", segs.monitoring.observed.monitor ?? "");

// 6 adapting
segs.adapting.closeup = { start_s: now(), end_s: null };
await scrollTo(".code");
if (await clickTab(2)) {
  await sleep(1000);
  await scrollTo(".code .note", 120);
  await sleep(4000);
  segs.adapting.observed.diagnosis = await text(".code .note");
  segs.adapting.observed.diff_head = await text(".code .diff-head");
  if (!segs.adapting.observed.diff_head) segs.adapting.issues.push("v2 tab selected but no diff shown");
  await shot("adapting", "v1-v2-diff");
  const versions = await q(() => [...document.querySelectorAll(".code .tabs button")].map((b) => b.textContent));
  segs.adapting.observed.tabs = versions;
  if (versions.includes("v3") && (await clickTab(3))) {
    await sleep(3000);
    segs.adapting.observed.diagnosis_v3 = await text(".code .note");
    await shot("adapting", "v2-v3-diff");
  }
} else segs.adapting.issues.push("no v2 tab");
segs.adapting.closeup.end_s = now();
checkNumbers("adapting", `${segs.adapting.observed.diagnosis ?? ""}`);

// 7 final
segs.final.closeup = { start_s: now(), end_s: null };
const repairBlocks = await q(() =>
  [...document.querySelectorAll(".evidence h3")].filter((h) => h.textContent.startsWith("Repair candidate")).map((h) => h.textContent));
if (repairBlocks.length) {
  let lastY = -1;
  for (let i = 0; i < repairBlocks.length; i++) {
    await scrollTo({ h3: repairBlocks[i].slice(0, 20) }, 40);
    const y = await q(() => Math.round(window.scrollY));
    if (y === lastY) continue; // page bottom reached: this block is already in the previous frame
    lastY = y;
    await sleep(3500);
    await shot("final", `repair-v${i + 2}`);
  }
  segs.final.observed.repair_blocks = await q(() =>
    [...document.querySelectorAll(".evidence h3")].filter((h) => h.textContent.startsWith("Repair candidate"))
      .map((h) => h.closest(".metric-block")?.innerText.split("\n").slice(0, 4).join(" | ")));
} else {
  await scrollTo({ h3: "Adaptation" }, 40);
  await sleep(3500);
  segs.final.issues.push("no repair candidate block (no adaptation recorded)");
  await shot("final");
}
segs.final.observed.final_stage = await stageChip();
segs.final.closeup.end_s = now();
checkNumbers("final", `${segs.final.observed.final_stage}`);

// 9 closing header (recorded before the audit page so the dashboard state is not reset)
segs.closing.closeup = { start_s: now(), end_s: null };
await scrollTo(0);
await sleep(4000);
segs.closing.observed.replay_badge = await text(".header .badge.replay");
await shot("closing");
segs.closing.closeup.end_s = now();

// 8 audit (last in the video): verbatim stdout, rendered in a monospace dark page
if (args.audit && fs.existsSync(args.audit)) {
  segs.audit.closeup = { start_s: now(), end_s: null };
  const raw = fs.readFileSync(args.audit, "utf8");
  const esc = raw.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
  const colored = esc
    .replace(/^\[PASS\]/gm, '<span class="p">[PASS]</span>')
    .replace(/^\[FAIL\]/gm, '<span class="f">[FAIL]</span>')
    .replace(/^\[WARN\]/gm, '<span class="w">[WARN]</span>')
    .replace(/^(RESULT: .*)$/gm, '<span class="r">$1</span>');
  const cmd = `$ ${args.auditCmd ?? `uv run python scripts/audit_run.py ${args.run}`}`;
  await page.setContent(`<!doctype html><html><head><meta charset="utf-8"><title>audit_run.py ${args.run}</title>
<style>html,body{margin:0;background:#0b0e14;color:#c9d1d9;font:14px/1.5 ui-monospace,SFMono-Regular,Menlo,monospace}
.bar{background:#161b22;padding:8px 14px;color:#8b949e;font-size:12px;border-bottom:1px solid #30363d}
pre{margin:0;padding:16px 20px;white-space:pre-wrap;word-break:break-word}.c{color:#58a6ff}
.p{color:#3fb950}.f{color:#f85149}.w{color:#d29922}.r{color:#3fb950;font-weight:700}</style></head>
<body><div class="bar">terminal · captured stdout of scripts/audit_run.py (unmodified)</div>
<pre><span class="c">${cmd.replace(/</g, "&lt;")}</span>\n${colored}</pre></body></html>`);
  await sleep(1500);
  await q(() => window.scrollTo({ top: document.body.scrollHeight, behavior: "smooth" }));
  await sleep(1500);
  const resultLine = raw.split("\n").find((l) => l.startsWith("RESULT:")) ?? null;
  segs.audit.observed.result_line = resultLine;
  const lines = raw.split("\n");
  const i6 = lines.findIndex((l) => /^\[\w+\] 6\./.test(l));
  const check6 = [];
  for (let j = i6 + 1; i6 >= 0 && j < lines.length && lines[j].startsWith("       "); j++) check6.push(lines[j]);
  segs.audit.observed.check6 = i6 < 0 ? null : [lines[i6], ...check6];
  if (!resultLine) segs.audit.issues.push("no RESULT line in audit output");
  else if (!/PASS \(7 pass, 0 warn, 0 fail\)/.test(resultLine)) segs.audit.issues.push(`audit result differs from the script: ${resultLine}`);
  await page.screenshot({ path: path.join(args.out, "audit.png"), fullPage: true });
  segs.audit.screenshots.push({ file: "audit.png", video_t_s: now() });
  log("screenshot audit.png");
  await sleep(3500);
  segs.audit.closeup.end_s = now();
} else segs.audit.issues.push("no audit output supplied (--audit)");

const recordedEnd = now();
mark("end");

// ---------------------------------------------------------------- save
const video = page.video();
await ctx.close();
const webm = path.join(args.out, "demo.webm");
await video.saveAs(webm);
await browser.close();
fs.rmSync(VIDEO_TMP, { recursive: true, force: true });

const order = ["intro", "discovery", "readiness", "authoring", "monitoring", "adapting", "final", "closing", "audit"];
const out = {
  run_id: args.run,
  plan: args.segments,
  video: "demo.webm",
  viewport: "1600x1000",
  color_scheme: "dark",
  recorded_at: new Date(T0).toISOString(),
  recorder_clock_length_s: recordedEnd,
  offsets_note:
    "All *_s values are seconds from the start of demo.webm (recorder clock started when the page, and so the video, was created; skew is typically < 0.3 s). " +
    "'live' = the moment the replay itself showed this segment; 'closeup' = a held view of the final state after pass B ended (docs/DEMO_SCRIPT.md: 'use that state for the code diff and evidence close-ups').",
  passes: {
    A: { speed: args.speedA, start_s: markers.find((m) => m.kind === "pass_A_start")?.t ?? 0, end_s: passBStart,
      used_for: "intro, discovery, readiness" },
    B: { speed: args.speedB, start_s: passBStart, end_s: passBEnd, used_for: "authoring, G2, monitoring, adapting, final",
      editor_cut: { start_s: passBStart, end_s: cutEnd,
        why: "Restart Replay re-emits the run from the first event; this stretch repeats discovery at the pass B speed. The script says to cut between passes in editing." } },
  },
  speed_note: args.speedNote ?? null,
  recording_order: order,
  segments: order.map((k) => segs[k]),
  markers,
  page_errors: pageErrors,
};
fs.writeFileSync(path.join(args.out, "segments.json"), JSON.stringify(out, null, 2));
log(`saved ${webm}`);
const issues = order.flatMap((k) => segs[k].issues.map((i) => `${k}: ${i}`));
console.log(JSON.stringify({ webm, recorder_clock_length_s: recordedEnd, issues }));
