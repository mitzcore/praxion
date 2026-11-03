# Demo film: structure and camera shot list

Written 2026-11-03; visual direction revised the same day: Mithran wants a beautiful, cinematic graphical treatment (reference: 3D cutaway industrial diagrams with labelled colour-coded flows) of the existing world of machines and how the AI is infused to generate and repair controllers; the captured footage is a small part. Demo production is the LAST task, after test and validation; nothing is produced before the direction is agreed. The film is 3 minutes. Everything shown must have happened; camera footage of
the board is labelled with the run it belongs to, or as "illustration of the rig" if it is not from a
scored run.

## Structure

| Beat | Length | Source |
|---|---|---|
| Problem: the existing world of machines (plants, pumps, heaters) and what happens when one changes | 35 s | cinematic cutaway-style graphics (direction to be agreed with Mithran; Higgsfield allowed) |
| Solution: how the AI is infused: discover → author → gate → deploy → detect → diagnose → repair → re-gate, trust boundary drawn | 45 s | same visual system, diagram that argues (shape = behaviour, colour = purpose) |
| Simulation evidence: dashboard replay of the best tank run (`v13-s11`), gate results, code diff | 45 s | `scripts/record_demo.py` on the stored run |
| Hardware evidence: phone footage of the TCLab run cut with the synced dashboard | 40 s | operator's phone + screen capture |
| Honest results and limits: relay rival wins on post-change MAE, one hardware distribution point, next steps | 15 s | same visual system |

## Decision: re-run on camera (recommended) or film an illustration

- **Re-run (hardware run 3, label `hw3`)**: real footage of a real run and a second hardware data
  point. ~80 min, operator in the room for one action at ~minute 11 (fan on, when the Mac alerts).
  Board at room temperature first (unplug 30 min before). Same fan position as run 2 (far corner,
  pointing away, shield 20 cm from the board; 1.32× loss). If it fails, run 2 stays the cited run.
- **Illustration**: 3 min of the board warming and the fan coming on, labelled "illustration of the
  rig"; all numbers from the run 2 bundle.

## Shot list (phone)

1. Setup: landscape, tripod or books, 1080p/30 fps, tap-and-hold to lock focus and exposure, side
   light, no window behind the board, cables tidy, fan edge visible in frame.
2. Clip 1, start (2 min): show the laptop clock to the lens for 3 s (sync), then the board as the
   first heater pulse starts (LED glow).
3. Clip 2, disturbance (4 min): start when the Mac alert fires, clock for 3 s, hand switches the fan
   on, keep rolling 3 more minutes.
4. Clip 3, finish (2 min): clock, then the board in the last minutes with v2 holding target.
5. Stills: overhead of the board; wide of laptop + board + fan + shield; close of power jack + USB.
6. Do not film the screen; the dashboard is captured directly and aligned to the clock shots.

Drop everything into `artifacts/demo/footage/` (not committed). Then: cut, diagrams, dashboard sync,
and voice-over offsets in `docs/DEMO_SCRIPT.md`.
