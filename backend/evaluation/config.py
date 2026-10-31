"""Evaluation constants.

###########################################################################################
# FROZEN. These values are fixed BEFORE any scoring run (CLAUDE.md rule 6, plan 5.4/10).  #
# Changing any of them invalidates every previously recorded score and must be logged in  #
# docs/IMPLEMENTATION_STATUS.md with a reason. Never tune these to make a result look     #
# better. Held-out (1000s) and disturbance (2000s) seeds are evaluator-only and must      #
# never appear in anything agent-facing.                                                  #
###########################################################################################
"""
from __future__ import annotations

TARGET = 0.60
BAND = (0.55, 0.65)
EPISODE_S = 120.0
SETTLE_S = 30.0

# Seed semantics (plant identity is separate from the scenario; see PlantAdapter.reset):
# - EXPLORATION_SEEDS are PLANT seeds: each live run discovers ONE machine, reset(seed=<plant>).
# - HELDOUT_SEEDS and DISTURBANCE_SEEDS are SCENARIO seeds applied to that run's plant seed,
#   reset(seed=<plant>, scenario=<1000s/2000s>): same machine, hidden initial level, noise and
#   disturbance magnitudes. The evaluator tests "this machine on hidden scenarios".
HELDOUT_SEEDS = list(range(1000, 1010))
DISTURBANCE_SEEDS = list(range(2000, 2005))
EXPLORATION_SEEDS = list(range(1, 21))

DISTURBANCE_AT_S = 60.0
DISTURBANCE_EPISODE_S = 300.0  # was 180.0; changed 2026-10-31 before any official scoring, see IMPLEMENTATION_STATUS decisions

GATE2_MIN_PASS = 8
GATE2_MIN_INBAND = 0.70
GATE3_MIN_PASS = 3
GATE3_MIN_MAE_REDUCTION = 0.20

DEGRADATION_WINDOW_S = 15.0
DEGRADATION_FACTOR = 2.0
DEGRADATION_FLOOR = 0.05
DEGRADATION_HOLD_S = 10.0

IN_BAND_SUSTAIN_S = 10.0

# Disturbance families by kind. "offset" families shift the steady-state operating point; any
# controller with integral action is expected to reject them by feedback alone, so the degradation
# monitor should NOT fire and no repair is expected. "dynamics" families change the loop dynamics
# (extra transport delay + slower actuator) and break the stability margin of an aggressively tuned
# loop; these are the families expected to require a repair (Gate 3).
DISTURBANCE_FAMILIES = {
    "pump_derate": "offset",
    "extra_leak": "offset",
    "drain_shift": "offset",
    "actuator_lag": "dynamics",
}
