// Praxion demo diagrams: deterministic timeline scheduler shared by the three clips.
//
// Diagram.run({name, duration, steps, tick}) where each step is
//   {t, label, on:[ids], off:[ids], add:{id: cls}, remove:{id: cls}, caption, captionClass, fn}
// Steps fire when elapsed seconds >= t (elapsed = performance.now() since start, no randomness).
// tick(t) is called every frame with the clamped elapsed time for continuous drawing (traces).
//
// URL parameters:
//   ?autoplay=1   start on load (used by scripts/render_diagrams.mjs); sets window.__done at the end
//   ?t=12.5       render the state at 12.5 s with transitions disabled (stills, layout checks)
//   (none)        show t = 0; click or press space to play
// Exposes window.__timeline = [{t_seconds, label}], window.__duration, window.__startEpochMs.
(function () {
  "use strict";
  const params = new URLSearchParams(location.search);
  window.__done = false;

  function el(id) {
    const e = document.getElementById(id);
    if (!e) throw new Error("diagram: no element #" + id);
    return e;
  }

  let capSlot = 0;
  function setCaption(html, cls) {
    const slots = [el("cap0"), el("cap1")];
    const cur = slots[capSlot];
    const next = slots[1 - capSlot];
    next.className = "cap" + (cls ? " " + cls : "");
    next.innerHTML = html || "";
    cur.classList.remove("on");
    if (html) next.classList.add("on");
    capSlot = 1 - capSlot;
  }

  function doStep(s) {
    (s.on || []).forEach((id) => { const e = el(id); e.classList.remove("off"); e.classList.add("on"); });
    (s.off || []).forEach((id) => { const e = el(id); e.classList.remove("on"); e.classList.add("off"); });
    Object.entries(s.add || {}).forEach(([id, c]) => c.split(" ").forEach((k) => el(id).classList.add(k)));
    Object.entries(s.remove || {}).forEach(([id, c]) => c.split(" ").forEach((k) => el(id).classList.remove(k)));
    if (s.caption !== undefined) setCaption(s.caption, s.captionClass);
    if (s.fn) s.fn();
  }

  window.Diagram = {
    run(cfg) {
      const { name, duration, steps } = cfg;
      const tick = cfg.tick || function () {};
      document.title = name;
      const sorted = steps.slice().sort((a, b) => a.t - b.t);
      window.__timeline = sorted.map((s) => ({ t_seconds: s.t, label: s.label }));
      window.__duration = duration;
      let applied = 0;
      const applyUpTo = (t) => {
        while (applied < sorted.length && sorted[applied].t <= t) doStep(sorted[applied++]);
      };

      const seek = params.get("t");
      if (seek !== null) {
        const t = Math.max(0, Math.min(duration, Number(seek)));
        document.documentElement.classList.add("instant");
        applyUpTo(t);
        tick(t);
        void document.body.offsetHeight;
        window.__done = true;
        return;
      }

      tick(0);
      let started = false;
      const start = () => {
        if (started) return;
        started = true;
        const hint = document.getElementById("hint");
        if (hint) hint.remove();
        const t0 = performance.now();
        window.__startEpochMs = performance.timeOrigin + t0;
        const frame = (now) => {
          const t = (now - t0) / 1000;
          applyUpTo(t);
          tick(Math.min(t, duration));
          if (t >= duration) { window.__done = true; return; }
          requestAnimationFrame(frame);
        };
        requestAnimationFrame(frame);
      };
      if (params.get("autoplay") === "1") {
        // two frames so the first paint (white stage) lands before t = 0
        requestAnimationFrame(() => requestAnimationFrame(start));
      } else {
        const hint = document.createElement("div");
        hint.id = "hint";
        hint.className = "hint";
        hint.textContent = "click or press space to play";
        document.getElementById("stage").appendChild(hint);
        document.addEventListener("click", start);
        document.addEventListener("keydown", (e) => { if (e.code === "Space") start(); });
      }
    },
  };
})();
