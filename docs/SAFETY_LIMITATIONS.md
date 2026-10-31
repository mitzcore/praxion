# Safety limitations

Praxion's safety layer is a simulation-level demonstration. Read these limits before trusting any claim.

## Layers that exist (trusted code)
1. **High-level interlock** (`Observation.interlock_high`, `INTERLOCK_LEVEL = 0.90`): forces `u = 0`; the runtime then calls `plant.emergency_stop()` (pump power cut and inlet closed, which flushes the actuator delay line).
2. **Analog hard cutoff**: `y >= hard_cutoff` (0.90) on the noisy sensor forces `u = 0` and the same emergency stop.
3. Stale or missing sensor, e-stop, and non-finite requests also force `u = 0`. Out-of-range requests are clamped.
4. **Exploration worst-case envelope** (`safety/envelope.py`): rejects constant-input proposals whose crude forward bound would reach `soft_high_limit` (0.85).

## Known limitations
- **The interlock is an ideal model.** It reads the true simulated level with no noise, no delay, no hysteresis and no failure modes. A real float switch can stick, chatter or fail. Containment after a trip is also ideal: inflow stops on the next 0.1 s tick. Even so, the true level can briefly exceed 0.90 by up to about 0.01, so hard violations are still counted against the controller.
- **The worst-case envelope ignores commands already queued in the delay line.** It bounds only the proposed constant input from the current measured level. It assumes no lag and does not account for higher commands issued before the proposal that are still in transit (up to `delay_nominal` + 22 s under `actuator_lag`). It also starts from the noisy `y`, not the true level.
- **The supervisor's `y`-based cutoff is late under measurement or actuator delay.** It reacts only after the measured level crosses 0.90. Under `actuator_lag` (18–22 s extra transport delay), the default PID reached h = 1.0 (overflow) on many plant × scenario combinations before the interlock existed, including plant 1 on every frozen disturbance scenario. A reactive cutoff cannot undo inflow that is already committed. That is why the independent interlock plus the delay-line flush exists.
- **Overrides and violations are scored against the candidate.** A forced safe stop never counts as the controller obeying constraints.
- **A repair is specific to the change it was written for.** Promoted repairs detune for the measured delay and then absorb offset changes (weaker pump, extra leak) far worse than the original controller did (`docs/BENCHMARKS.md`, offset-family rows for repaired candidates). A machine that reverts or changes in a second way needs another monitored repair cycle; the system does not keep a library of controllers or switch between them.
- **Simulation establishes nothing about real hardware.** All dynamics, delays, noise and the interlock are models with seeded parameters. No claim made here transfers to a physical tank, pump or sensor without separate validation.
