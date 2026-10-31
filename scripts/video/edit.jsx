// Praxion demo film: Higgsedit (Higgsfield native motion-design CLI) edit script.
// Every data shot is a real chart or dashboard frame from run v13-s11-20261031-020922-a0e68e.
// Build in the Higgsfield sandbox:  higgsedit fonts add . "DM Sans" "DM Sans:700" && higgsedit build edit.jsx
// Then ./finish.sh renders, mixes the narration from timing.json, and muxes renders/praxion_demo.mp4.
import fs from "node:fs";

const W = 1920, H = 1080;
const BG = "#0b1220", FG = "#edf2ff", MUTED = "#8ea0bf", AMBER = "#f4c677", GREEN = "#7be5b6", RED = "#ff6b6b";
const FONT = "DM Sans";

function loadTiming() {
  try { return JSON.parse(fs.readFileSync("timing.json", "utf8")); }
  catch { return Array.from({ length: 9 }, (_, i) => ({ start: i * 8, dur: 8 })); }
}

export default async ({ project }) => {
  const T = loadTiming();
  const total = T[8].start + T[8].dur;
  const p = await project({ dir: ".", size: `${W}x${H}`, fps: 30, background: BG });

  const img = {};
  for (const n of ["01_v1_nominal", "02_v1_after_change", "03_v1_vs_v2", "04_five_machines",
                   "05_dashboard_discovery", "06_dashboard_code_v1", "07_dashboard_diff_diagnosis",
                   "08_dashboard_evidence", "09_audit"]) img[n] = await p.add(`media/${n}.png`);
  const replay = await p.add("media/dashboard_replay.mp4");
  let tank = null;
  if (fs.existsSync("media/tank.mp4")) tank = await p.add("media/tank.mp4");

  const kicker = (t) => (
    <text width={1200} height={40} fontFamily={FONT} fontSize={24} fontWeight={700} letterSpacing={4} color={MUTED}>{t}</text>
  );
  const title = (t, size = 56) => (
    <text width={1760} height={size * 1.3} fontFamily={FONT} fontSize={size} fontWeight={700} color={FG}>{t}</text>
  );
  const caption = (t, color = MUTED) => (
    <text width={1760} height={44} fontFamily={FONT} fontSize={28} fontWeight={400} color={color}>{t}</text>
  );
  const chip = (t, color) => (
    <frame width="hug" height="hug" padding={{ top: 10, bottom: 10, left: 18, right: 18 }} background="#121c30" radius={10} layout="row">
      <text width="hug" height={34} fontFamily={FONT} fontSize={26} fontWeight={700} color={color}>{t}</text>
    </frame>
  );
  const enter = { enter: { from: { y: 20, opacity: 0 }, duration: 0.5 }, exit: { to: { opacity: 0 }, duration: 0.35, anchor: "end" } };

  // A full-screen beat: kicker + headline on top, media in the middle, caption/chips at the bottom.
  function beat(i, { k, h, media, mediaW = 1760, mediaH = 780, cap, chips = [], wipe = false, zoom = true, media2 = null }) {
    const { start, dur } = T[i];
    const mediaNode = media2 ?? (
      <media file={media} width={mediaW} height={mediaH} fit="contain" radius={14}
        animate={zoom ? [{ property: "scale", from: 1.0, to: 1.04, duration: dur, easing: "linear" }] : []} />
    );
    p.compose(
      <frame width={W} height={H} padding={{ top: 56, bottom: 48, left: 80, right: 80 }} gap={18} background={BG} motion={enter}>
        <frame width="fill" height="hug" gap={8}>
          {kicker(k)}
          {title(h, 46)}
        </frame>
        <frame width="fill" height={mediaH} align="center" justify="center" origin="center"
               reveal={wipe ? { from: "left", at: 0.3, duration: Math.min(2.6, dur * 0.45), easing: "ease-in-out" } : undefined}>
          {mediaNode}
        </frame>
        <frame width="fill" height="hug" layout="row" gap={14} align="center">
          {chips.map(([t, c]) => chip(t, c))}
        </frame>
        {cap ? caption(cap) : null}
      </frame>,
      { at: start, dur, name: `beat${i + 1}` }
    );
  }

  // Beat 1: generated tank shot (if present) then title card.
  {
    const { start, dur } = T[0];
    const clipDur = tank ? 5 : 0;
    if (tank) p.cut(tank, { from: 0, dur: clipDur, at: start, fit: "cover" });
    if (tank) p.compose(
      <frame width={W} height={H} padding={{ top: 56, bottom: 64, left: 80, right: 80 }} justify="space-between">
        {kicker("THE MACHINE, BEFORE")}
        <frame width="fill" height="hug" gap={10}>
          <text width={1700} height={70} fontFamily={FONT} fontSize={54} fontWeight={700} color={FG}>Every machine has a controller. Someone had to write it.</text>
          <text width={1700} height={40} fontFamily={FONT} fontSize={28} color={MUTED}>A tank. A pump. A drain. Hold the water at 60%.</text>
        </frame>
      </frame>,
      { at: start, dur: clipDur }
    );
    p.compose(
      <frame width={W} height={H} background={BG} align="center" justify="center" gap={20} motion={enter}>
        <text width={1400} height={160} fontFamily={FONT} fontSize={132} fontWeight={700} color={FG} align="center" letterSpacing={-4}>Praxion</text>
        <text width={1400} height={50} fontFamily={FONT} fontSize={36} color={MUTED} align="center">An AI engineer for machines that change.</text>
        <text width={1400} height={40} fontFamily={FONT} fontSize={24} color={MUTED} align="center">Built on Meta Muse. Every curve in this film is from one recorded run.</text>
      </frame>,
      { at: start + clipDur, dur: dur - clipDur }
    );
  }

  beat(1, { k: "02 · WHAT PRAXION DOES", h: "Experiments, then hypotheses, then it writes the controller itself",
            media: null, zoom: false,
            media2: <media file={replay} trimStart={16} width={1760} height={780} fit="contain" radius={14} />,
            cap: "Real dashboard replay: Muse proposes each experiment, records its beliefs, then authors controller_v1.py" });
  beat(2, { k: "03 · IT WORKS", h: "Hidden scenario the AI never saw: level rises and holds the 60% line",
            media: img["01_v1_nominal"], wipe: true, mediaH: 760,
            chips: [["10 / 10 hidden tests passed", GREEN], ["median error 0.013", FG], ["0 safety violations", GREEN]] });
  beat(3, { k: "04 · THE MACHINE CHANGES", h: "A 24-second delay appears. Nobody tells the AI.",
            media: img["02_v1_after_change"], wipe: true, mediaH: 760,
            chips: [["same controller v1", AMBER], ["swings to the overflow line", RED], ["watchdog fires at 89.5 s", AMBER]] });
  beat(4, { k: "05 · IT REPAIRS ITSELF", h: "Measures the new delay, names the cause, rewrites its own code",
            media: img["07_dashboard_diff_diagnosis"], mediaH: 760,
            cap: "Muse, in its own words: \"Same u now acts ~24 s later ... Td_old <1 s, Td_new ~24 s.\"  Diagnosis category: response_slower (matched the hidden fault)" });
  beat(5, { k: "06 · PROOF ON THE SAME TEST", h: "v1 before repair vs v2 after repair, identical hidden scenario",
            media: img["03_v1_vs_v2"], wipe: true, mediaH: 760,
            chips: [["error 0.217 to 0.020  (-90%)", GREEN], ["100% in band", GREEN], ["overflow trips 2 to 0", GREEN]] });
  beat(6, { k: "07 · NOT A LUCKY RUN", h: "Five different hidden machines",
            media: img["04_five_machines"], wipe: true, mediaH: 760,
            chips: [["5 / 5 repaired", GREEN], ["0 safety violations", GREEN], ["about $1.75 and 12 min each", FG]] });
  beat(7, { k: "08 · FOR THE ENGINEERS", h: "Sandboxed code. Blind agent. Independent audit.",
            media: img["09_audit"], mediaH: 700,
            cap: "Docker: no network, read-only, no privileges · the model never sees plant parameters or test seeds · 7/7 audit: byte-identical authorship, no leaks · one command regenerates every number" });
  {
    const { start, dur } = T[8];
    p.compose(
      <frame width={W} height={H} background={BG} align="center" justify="center" gap={22} motion={enter}>
        <text width={1500} height={150} fontFamily={FONT} fontSize={120} fontWeight={700} color={FG} align="center" letterSpacing={-4}>Praxion</text>
        <text width={1500} height={50} fontFamily={FONT} fontSize={38} color={FG} align="center">Learn. Write. Test. Break. Diagnose. Repair. Prove.</text>
        <text width={1500} height={36} fontFamily={FONT} fontSize={22} color={MUTED} align="center">Simulation only. Repairs are conservative. Hand-tuned expert controllers still lead on the changed machine. github.com/mitzcore/praxion</text>
      </frame>,
      { at: start, dur }
    );
  }

  console.log("timeline", p.duration(), "planned", total);
  for (const [t, name] of [[2, "b1"], [T[0].start + 8, "b1t"], [T[4].start + 3, "b5"], [T[7].start + 3, "b8"], [T[8].start + 2, "b9"]])
    await p.frame(t, `renders/${name}.png`);
};
