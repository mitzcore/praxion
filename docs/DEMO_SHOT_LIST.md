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

## Decided 2026-11-03: fan A/B on the hardware run (`hw2`), filmed

Order agreed with Mithran: overnight batch → fan A/B → film look decision. The fan A/B measures the
promoted repair of run `hw2-20261103-074537-698ba8` against its frozen v1 on the physical board, under
the same change the run experienced (operator-applied fan), and writes `board_verification.json` into
that bundle (audited by `scripts/audit_run.py` check 8). The batch is paused at a run boundary before
the session (`artifacts/batch_logs/BATCH_STOP`, then resumed with `--start <next run>`).

Command (Claude runs it; alerts by macOS notification and voice):

```
uv run python scripts/verify_on_board.py --run hw2-20261103-074537-698ba8 \
  --port /dev/cu.usbmodem1101 --disturbance operator --order v1,v2
```

Session timeline (about 55 min, two trials, each: cool to < 30 °C, 480 s nominal, fan, 600 s):

| cue | what the Mac says | what Mithran does |
|---|---|---|
| T0 | (cool-down, up to 10 min) | board at room temperature, fan OFF, same fan position as run 2 (far corner, pointing away, shield 20 cm; 1.32× loss) |
| T0 + ~8 min | "Apply the physical disturbance now" | fan ON, then say "go" (Claude creates `OPERATOR_GO`) |
| T0 + ~18 min | "Turn the disturbance OFF before the next trial" | fan OFF, then say "off" (Claude creates `OPERATOR_OFF`) |
| + cool-down + ~8 min | "Apply the physical disturbance now" | fan ON, say "go" |
| + 10 min | "Session complete: turn the disturbance OFF now" | fan OFF |

The trial under way is printed in the terminal (`v1` first, then `v2`). The dashboard does not follow a
script-driven session live; it is re-recorded afterwards from the bundle (board events replay in order).

## Shot list (phone)

1. Setup: landscape, tripod or books, 1080p/30 fps, tap-and-hold to lock focus and exposure, side
   light, no window behind the board, cables tidy, fan edge visible in frame.
2. Clip A (per trial, 4 min): start when the Mac says "Apply the physical disturbance now": laptop
   clock to the lens for 3 s (sync), hand switches the fan on, keep rolling 3 more minutes. Two trials,
   two clips; name them `v1-fan.mp4` and `v2-fan.mp4` by the trial printed in the terminal.
3. Clip B (per trial, 1 min): clock, then the board in the last minute of the 600 s window (v1
   drifting, v2 holding, whatever the board actually does).
4. Clip C (1 min, once): the terminal as the result table prints (hashes, board MAE, twin prediction).
5. Stills: overhead of the board; wide of laptop + board + fan + shield; close of power jack + USB.
6. Do not film the dashboard; it is captured directly from the bundle and aligned to the clock shots.

Drop everything into `artifacts/demo/footage/` (not committed). Then: cut, diagrams, dashboard sync,
and voice-over offsets in `docs/DEMO_SCRIPT.md`.
