# Demo film production (2026-11-04)

The 3-minute submission film is assembled from this folder. Every number on screen is listed with its source in `SPEC.md`; the motion-graphic scenes are plain HTML + SVG + vanilla JS (`scenes/`), rendered deterministically with headless Chromium (`render/render_scenes.mjs`, Playwright from `frontend/node_modules`), then cut together with ffmpeg by `assemble.py`.

Inputs that are not in the repo (large or personal): phone footage of the board session (`artifacts/demo/footage/`), dashboard screenshots (`artifacts/demo/stills/`), the dashboard replay (`artifacts/demo/v13-s11-…-r3/demo.webm`), two generated B-roll clips labelled "background: illustration" on screen (Google Veo 3.1 via Higgsfield; a pump room and a data-centre aisle; never used for evidence), a generated instrumental music bed (ElevenLabs Music via Higgsfield) and the narration (Seed Audio TTS). Those live in `artifacts/demo/film/` on the production machine and are gitignored.

Reproduce the scenes: `node demo/film/render/render_scenes.mjs --out /tmp/scenes`. Check a still: open any scene with `?t=12.5`.
