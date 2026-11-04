// Render film scenes (scratchpad/film/scenes/*.html) to 1920x1080 30 fps .mp4 (H.264) files.
//   node render_scenes.mjs [--only a,b] [--out <dir>]
// Each scene: headless Chromium, Playwright recordVideo, ?autoplay=1, wait for window.__done,
// then trim pre-roll and re-encode to constant 30 fps. Writes <name>.timing.json.
import { createRequire } from "node:module";
import { execFileSync } from "node:child_process";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const SCENES = path.resolve(HERE, "..", "scenes");
const require = createRequire("/Users/mitz/projects/praxion/frontend/package.json");
const { chromium } = require("playwright");
const W = 1920, H = 1080, FPS = 30;

const args = { only: null, out: path.resolve(HERE, "..", "out") };
for (let i = 2; i < process.argv.length; i++) {
  const k = process.argv[i];
  if (k === "--only") args.only = process.argv[++i].split(",").map((s) => s.trim()).filter(Boolean);
  else if (k === "--out") args.out = path.resolve(process.argv[++i]);
  else throw new Error(`unknown arg ${k}`);
}
const names = args.only || fs.readdirSync(SCENES).filter((f) => f.endsWith(".html")).map((f) => f.slice(0, -5)).sort();
fs.mkdirSync(args.out, { recursive: true });

function probeDuration(file) {
  return Number(execFileSync("ffprobe", ["-v", "error", "-show_entries", "format=duration",
    "-of", "default=noprint_wrappers=1:nokey=1", file], { encoding: "utf8" }).trim());
}

async function render(browser, name) {
  const html = path.join(SCENES, `${name}.html`);
  if (!fs.existsSync(html)) throw new Error(`missing ${html}`);
  const tmp = path.join(args.out, `.tmp_${name}`);
  fs.rmSync(tmp, { recursive: true, force: true });
  fs.mkdirSync(tmp, { recursive: true });
  const context = await browser.newContext({ viewport: { width: W, height: H }, deviceScaleFactor: 1,
    recordVideo: { dir: tmp, size: { width: W, height: H } } });
  const errors = [];
  const page = await context.newPage();
  page.on("pageerror", (e) => errors.push(String(e)));
  page.on("console", (m) => { if (m.type() === "error") errors.push(m.text()); });
  await page.goto(pathToFileURL(html).href + "?autoplay=1");
  const duration = await page.evaluate(() => window.__duration);
  await page.waitForFunction(() => window.__done === true, null, { timeout: (duration + 60) * 1000, polling: 100 });
  const timeline = await page.evaluate(() => window.__timeline);
  const startEpochMs = await page.evaluate(() => window.__startEpochMs);
  await page.waitForTimeout(500);
  const video = page.video();
  const closeMs = Date.now();
  await context.close();
  const raw = await video.path();
  if (errors.length) throw new Error(`${name}: page errors: ${errors.join(" | ")}`);
  const dRaw = probeDuration(raw);
  const videoStartMs = closeMs - dRaw * 1000;
  const offset = Math.max(0, (startEpochMs - videoStartMs) / 1000);
  const out = path.join(args.out, `${name}.mp4`);
  fs.rmSync(out, { force: true });
  execFileSync("ffmpeg", ["-hide_banner", "-loglevel", "error", "-y", "-ss", offset.toFixed(3), "-i", raw,
    "-t", String(duration), "-vf", `fps=${FPS},scale=${W}:${H}:flags=lanczos,format=yuv420p`,
    "-c:v", "libx264", "-preset", "medium", "-crf", "17", "-an", out], { stdio: "inherit" });
  fs.rmSync(tmp, { recursive: true, force: true });
  fs.writeFileSync(path.join(args.out, `${name}.timing.json`), JSON.stringify(timeline, null, 2) + "\n");
  return { name, out, duration, measured: probeDuration(out), offset };
}

const browser = await chromium.launch({ headless: true });
try {
  for (const n of names) {
    process.stdout.write(`rendering ${n} ... `);
    const r = await render(browser, n);
    console.log(`${r.measured.toFixed(2)} s (page ${r.duration} s, pre-roll ${r.offset.toFixed(2)} s) -> ${r.out}`);
  }
} finally {
  await browser.close();
}
