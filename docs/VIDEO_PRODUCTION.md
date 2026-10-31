# Demo film production (Higgsfield motion designer)

Output: `artifacts/video/praxion_demo.mp4` (1920×1080, 30 fps, 2:58, H.264 + AAC narration). Not in git (130 MB); attach to the submission and investor decks.

## What is in it
Nine beats per `docs/VIDEO_STORYBOARD.md`. All data shots are real:
- Charts rendered from run `v13-s11-20261031-020922-a0e68e` by `scripts/video/make_video_assets.py` (nominal hold, failure after the hidden change, v1 vs v2 on the identical scenario, five-machine before/after).
- Dashboard frames and the replay clip from `scripts/record_demo.py` for the same run.
- The audit screenshot (`scripts/audit_run.py`, 7/7).
The only generated footage is the 5-second opening tank shot (Seedance 2.5 via Higgsfield, 35 credits). Narration is text-to-speech (Seed Audio, voice "Arthur") from the storyboard lines; 9 lines, about 4 credits. Total Higgsfield spend: 47.8 credits.

## Reproduce
1. `uv run --with matplotlib python scripts/video/make_video_assets.py` → `artifacts/video/assets/0*.png`.
2. Copy the dashboard stills and `demo.mp4` from `artifacts/demo/<run>/` into the assets folder as listed in the storyboard.
3. In the Higgsfield sandbox (`sandbox_exec`), create `/home/user/praxion/{media,media/vo,renders}`, download the assets, the generated tank clip as `media/tank.mp4`, and the nine narration MP3s as `media/vo/vo1..9.mp3`.
4. Regenerate `timing.json` (each beat = max(minimum, 0.6 s + narration + 0.9 s)); the committed file matches the shipped film.
5. `higgsedit fonts add . "DM Sans" "DM Sans:700" && higgsedit build edit.jsx` (frames for review), then `./finish.sh` (render, mix, mux). Upload with a presigned URL from `media_upload` and confirm with `media_confirm`.

## Editing notes
- Glyphs: the vendored DM Sans lacks arrows and the minus sign; keep text ASCII.
- Beat 2 shows the real replay from 16 s in (discovery experiments landing and the ledger filling).
- Beat 5's dashboard frame is dense by design: the point is that the diagnosis and the diff are real; the caption carries the quote.
