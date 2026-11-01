# TCLab hardware runbook (MVP-2)

Everything below was rehearsed on the TCLab simulator on 2026-11-01 (`tclabsim1`, `tclabsim2`, `tclabsim-weak`). The hardware path differs only in the plant class and in real time: a full run takes about 60 to 75 minutes of wall clock.

## Before you start
- Board on a non-flammable surface, both heater plates uncovered, nothing touching them. Plates reach 60 to 70 °C; do not touch during a run.
- Plug the TCLab's barrel-jack power supply in (heaters) and the USB cable (data). Both LEDs on.
- Find the serial port: `ls /dev/tty.usbmodem*` on macOS. Pass it as `--port`.
- Props on the desk: a small USB fan (primary disturbance: faster heat loss), a piece of foam or a paper cup (secondary: slower sensor response).
- Room temperature between 15 and 30 °C; the normalization assumes 15 °C = 0.

## Smoke test (2 minutes)
```bash
uv run python - <<'EOF'
from backend.plant.tclab_plant import TCLabHardware
p = TCLabHardware(port="/dev/tty.usbmodemXXXX")
o = p.reset(1); print("T1 =", round(o.y*60+15, 1), "C")
for u in (0.0, 0.5, 0.0):
    for _ in range(10): o = p.step(u)
    print("u", u, "T1", round(o.y*60+15, 1), "interlock", o.interlock_high)
p.close()
EOF
```
Expect the temperature to rise about 1 °C during the 10 s at 50% and the interlock to be False. Heaters off at exit.

## The run (60 to 75 minutes)
```bash
uv run python scripts/run_live_demo.py --model muse-spark-1.3 --plant tclab --port /dev/tty.usbmodemXXXX \
  --eval-plant twin --disturbance extra_leak --label hw1
```
What happens, with approximate wall-clock times:
1. **Discovery, 15 to 25 min.** Up to 8 experiments of 60 to 180 s chosen by Muse. The board heats and cools. Do nothing.
2. **Twin fit, instant.** Trusted code fits a thermal model to the experiments; `twin_fit.json` is written. If the fit report has warnings, the run continues but note them.
3. **Authoring and gating, 2 to 4 min.** v1 is written, sandboxed, and scored on the twin. If G2 fails, Muse revises; each attempt is about 2 min.
4. **Deployment and monitoring, 10 min to the prompt.** v1 runs on the board. At 600 s (10 minutes) the terminal prints `>>> Apply the physical disturbance now, then press Enter`. **Switch the fan on, aim it at the heater plate from about 10 cm, press Enter.** Leave it on for the rest of the run.
5. **Detection, 1 to 5 min after the fan.** The monitor fires when the 60 s window error stays above 1.2 °C for 30 s.
6. **Re-identification, 10 to 20 min.** Up to 4 experiments on the changed machine. Do not touch the fan.
7. **Repair and re-scoring, 3 to 8 min.** v2 is authored, sandboxed, scored on the twin with the declared disturbance family, and promoted or rejected.
8. **Done.** Heaters off automatically. Bundle under `artifacts/runs/hw1-*`.

Declared family for the fan is `extra_leak`; for foam over the sensor use `--disturbance actuator_lag`. The family is used only to pick the twin's disturbance suite for the same-scenario v1 vs v2 comparison; it is never sent to the model.

## If something goes wrong
- `Ctrl-C` stops the run; the atexit hook turns heaters off. Verify both LEDs dim.
- Serial errors: unplug and replug USB, re-run `ls /dev/tty.usbmodem*`, restart.
- Monitor never fires after the fan: the fan is too weak or too far. Move it to 5 cm or add the foam on top. If it still does not fire within 10 min, the run ends COMPLETE with "no degradation detected", which is a valid honest result; rerun with a stronger disturbance.
- Twin fit warnings `K_at_bound` or `short_relative_to_tau`: Muse's experiments were too short. The run continues; mention it in the write-up.

## Afterwards
```bash
uv run python scripts/audit_run.py <run_id>
uv run python scripts/run_evaluation.py --sandbox docker     # adds the run to BENCHMARKS.md
uv run python scripts/record_demo.py --run <run_id>          # replay recording for the film
```
Add the hardware beat to the film only if the audit passes; the recorded verdict is whatever it is.
