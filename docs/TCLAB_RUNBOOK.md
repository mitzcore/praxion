# TCLab hardware runbook (MVP-2)

Rehearsed on the TCLab simulator on 2026-11-01 (`tclabsim1`, `tclabsim2`, `tclabsim-weak`, `tclabsim-fan*`) and on a fake board speaking the real serial protocol on 2026-11-02 (`docs/AUDIT_2026-11-02.md`). The hardware path differs from the simulator in the plant class and in real time: a full run takes about 60 to 75 minutes. The run's wall-clock budget is 3 h for `--plant tclab` (the simulator default of 30 min stopped a hardware run mid-repair on the fake board).

## Before you start

- Board on a non-flammable surface, both heater plates uncovered, nothing touching them. Plates reach 60 to 70 °C; do not touch during a run.
- Plug the TCLab's barrel-jack power supply in (heaters) and the USB cable (data; the cable in the box is a data cable). Both LEDs on. A USB-C to USB-A adapter is fine.
- **Cold board.** Start from room temperature. A board still warm from a previous run biases the twin fit (fitted ambient off by several °C with no warning).
- Find the serial port: `ls /dev/cu.usbmodem*` on macOS (use the `cu.` device, not `tty.`). Pass it as `--port`.
- Docker Desktop running (`docker info`), because the default `--sandbox docker` runs Muse's code in the container. Give it a minute after starting.
- Props: a small USB fan (primary disturbance: faster heat loss); a piece of foam or a paper cup (secondary: slower sensor response). A household room fan is far too strong even at 1.5 m and even aimed at a wall (measured 2026-11-02 in a 17 °C room: 4× the natural heat loss, board could not pass 40 °C at 80 % power). Place it as far away as the room allows, pointing away from the board, with a shield (book or box) 20 cm in front of the board; that gave 1.3× (pre-flight step 3 passes at 1.3× to 2×). The changed machine must still reach the target with the heater below full power, or the repair comparison is meaningless.
- Room between 15 and 30 °C; normalization is y = (T − 15)/60.
- Use a neutral `--label` (for example `hw1`). The label is part of the run id; it must not name the disturbance.
- Never close the terminal window during a run. Stop only with Ctrl-C. (Normal exit, Ctrl-C, SIGTERM and a closed window all turn the heater off now, but Ctrl-C is the path that also leaves a complete bundle.)

## Pre-flight (10 minutes)

1. Vendor diagnostic, confirms firmware and heater response (runs both heaters at 100 % for a short time):
   ```bash
   uv run python -c "import tclab; tclab.diagnose(port='/dev/cu.usbmodemXXXX')"
   ```
   Expect firmware ≥ 1.4 and T1 rising by at least 0.8 °C during the 30 s heater test.
2. Smoke test through our plant class (heaters off at exit):
   ```bash
   uv run python - <<'EOF'
   from backend.plant.tclab_plant import TCLabHardware
   p = TCLabHardware(port="/dev/cu.usbmodemXXXX")
   o = p.reset(1); print("T1 =", round(o.y*60+15, 1), "C")
   for u in (0.0, 0.5, 0.0):
       for _ in range(10): o = p.step(u)
       print("u", u, "T1", round(o.y*60+15, 1), "interlock", o.interlock_high)
   p.close()
   EOF
   ```
   Expect about 1 °C of rise during the 10 s at 50 % and `interlock False`.
3. **Fan check.** The monitor fires when the 60 s window error stays above 1.2 °C for 30 s. A weak fan against a well-tuned controller can stay under that. Measure: bring T1 to about 45 °C (u ≈ 0.4 for a few minutes), set u = 0, and log the drop over 60 s with the fan off and then with the fan on at 10 cm. If the fan adds less than about 30 % to the cooling rate, move it to 5 cm or add the foam on the sensor as well.
   ```bash
   uv run python - <<'EOF'
   import time
   from backend.plant.tclab_plant import TCLabHardware
   p = TCLabHardware(port="/dev/cu.usbmodemXXXX"); o = p.reset(1)
   while o.y*60+15 < 44.0: o = p.step(0.6)
   for label in ("fan OFF", "fan ON (switch it on now, 10 cm)"):
       input(f"{label}: press Enter to log 60 s of cooling at u=0")
       t0 = o.y*60+15
       for _ in range(60): o = p.step(0.0)
       print(label, "drop over 60 s:", round(t0 - (o.y*60+15), 2), "C")
       while o.y*60+15 < 44.0: o = p.step(0.6)
   p.close()
   EOF
   ```
4. Let the board cool below 35 °C before the run (the run's reset waits up to 120 s for that).

## The run (60 to 75 minutes)

```bash
uv run python scripts/run_live_demo.py --model muse-spark-1.3 --plant tclab --port /dev/cu.usbmodemXXXX \
  --eval-plant twin --disturbance extra_leak --label hw1
```

What happens, with approximate wall-clock times:

1. **Discovery, 15 to 25 min.** Up to 8 experiments of 60 to 180 s chosen by Muse. The board heats and cools. Do nothing. Rejected proposals count against the budget.
2. **Twin fit, instant.** Trusted code fits a thermal model to the experiments; `twin_fit.json` is written. Warnings are logged; the run continues.
3. **Authoring and gating, 2 to 4 min.** v1 is written, sandboxed and scored on the twin. If G2 fails, Muse revises; each attempt is about 2 min. The heater is off during this (event `actuator_idled`).
4. **Deployment and monitoring, 10 min to the prompt.** v1 runs on the board. At 600 s the terminal prints `>>> Apply the physical disturbance now, then press Enter (control keeps running)`. **Switch the fan on, aim it at the heater plate from about 10 cm, press Enter.** The controller keeps running while you do this; the first second after Enter is recorded as the disturbance time. Leave the fan on for the rest of the run. If the run was launched without a keyboard (from a tool or a service, stdin not a TTY), an EOF on stdin is **not** taken as Enter: the prompt instead names a trigger file, `artifacts/runs/<run_id>/OPERATOR_GO`, and the run waits until the operator creates it (`touch` it after switching the fan on). The event `operator_disturbance_prompt` records which mechanism was used.
5. **Detection, 1 to 5 min after the fan.** The monitor fires when the window error stays above 1.2 °C for 30 s. If it has not fired after 10 min the run ends COMPLETE with "no degradation detected", which is a valid, recorded result.
6. **Re-identification, 10 to 20 min.** Up to 4 experiments on the changed machine. Do not touch the fan.
7. **Repair and re-scoring, 3 to 8 min.** A second twin is fitted from the after-change experiments; frozen v1 and v2 are scored on it; v2 is promoted or rejected.
8. **Done.** Heater off and port closed automatically. Bundle under `artifacts/runs/hw1-*`.

Declared family for the fan is `extra_leak`; for foam over the sensor use `--disturbance actuator_lag`. The family is only a label and a fallback for the twin suite; it is never sent to the model.

## If something goes wrong

- `Ctrl-C` stops the run and turns the heater off. Verify the heater LED dims.
- Serial glitches: single missed or garbled replies are retried three times. If the port is really gone, the run is marked FAILED with the reason, heater off; unplug and replug USB, re-run `ls /dev/cu.usbmodem*`, restart.
- Monitor never fires after the fan: the fan is too weak or too far (pre-flight step 3). Move it to 5 cm or add the foam on top.
- Twin fit warnings `K_at_bound` or `short_relative_to_tau`: Muse's experiments were too short. The run continues; mention it in the write-up. Note that the warnings do not catch a warm board; that is why the board must be cold at the start.

## Afterwards

```bash
uv run python scripts/audit_run.py <run_id>
uv run python scripts/record_demo.py --run <run_id>          # replay recording for the film
```

`scripts/run_evaluation.py` scores tank runs only; a TCLab run is reported from its bundle (`evaluation_*.json`, `twin_fit*.json`, `adaptation_v2.json`) in the status doc and README, labeled as scored on the twin. Add the hardware beat to the film only if the audit passes; the recorded verdict is whatever it is.
