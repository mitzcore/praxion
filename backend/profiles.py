"""Plant profiles: every plant-specific timing, limit and unit lives here, so the orchestrator,
evaluator, monitor and prompts stay plant-agnostic.

The TANK profile reproduces the frozen constants used for every recorded benchmark run; changing
it invalidates recorded scores (see evaluation/config.py). The TCLAB profiles are new (2026-11-01)
for the physical heater: slower dynamics, one-second control period, temperature normalized so
20 °C → 0.0 and 80 °C → 1.0.
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

from backend.evaluation import config as C


class PlantProfile(BaseModel):
    name: Literal["tank", "tclab_sim", "tclab"]
    description_for_operator: str
    dt: float
    # objective (normalized units)
    target: float
    band: tuple[float, float]
    # evaluation windows
    episode_s: float
    settle_s: float
    disturbance_at_s: float
    disturbance_episode_s: float
    # exploration limits
    max_experiments: int
    min_experiments_before_generate: int
    max_single_experiment_s: float
    after_change_max_single_experiment_s: float
    worst_case_rate_per_unit_u: float  # envelope: normalized units per second at u = 1
    # safety limits (normalized)
    soft_high_limit: float
    hard_cutoff: float
    # monitoring
    monitor_window_s: float
    monitor_hold_s: float
    monitor_factor: float
    monitor_floor: float
    monitor_calibrate_s: float
    monitor_pre_s: float
    monitor_duration_s: float
    monitor_post_detection_s: float
    # display
    y_unit: str
    y_scale: float  # display = y * y_scale + y_offset
    y_offset: float

    def to_display(self, y: float) -> float:
        return y * self.y_scale + self.y_offset


TANK = PlantProfile(
    name="tank",
    description_for_operator="Simulated water tank (MVP-1). Frozen benchmark profile.",
    dt=0.1,
    target=C.TARGET, band=C.BAND,
    episode_s=C.EPISODE_S, settle_s=C.SETTLE_S,
    disturbance_at_s=C.DISTURBANCE_AT_S, disturbance_episode_s=C.DISTURBANCE_EPISODE_S,
    max_experiments=12, min_experiments_before_generate=3,
    max_single_experiment_s=20.0, after_change_max_single_experiment_s=40.0,
    worst_case_rate_per_unit_u=0.10,
    soft_high_limit=0.85, hard_cutoff=0.90,
    monitor_window_s=C.DEGRADATION_WINDOW_S, monitor_hold_s=C.DEGRADATION_HOLD_S,
    monitor_factor=C.DEGRADATION_FACTOR, monitor_floor=C.DEGRADATION_FLOOR,
    monitor_calibrate_s=58.0, monitor_pre_s=60.0, monitor_duration_s=300.0, monitor_post_detection_s=40.0,
    y_unit="level fraction", y_scale=1.0, y_offset=0.0,
)

# TCLab: T1 thermistor, heater Q1. Normalized y = (T - 15) / 60 (zero at 15 °C so cool rooms never clamp).
# Target 45 °C = 0.50; band ±1.5 °C. Soft limit 0.85 = 66 °C, hard cutoff 0.90 = 69 °C (TCLab firmware cuts at 100 °C).
# Heating rate at full power is roughly 0.15–0.25 °C/s near room temperature → ≤ 0.0042 /s normalized;
# the envelope uses 0.006 to stay conservative.
_TCLAB_COMMON = {
    "dt": 1.0,
    "target": (45.0 - 15.0) / 60.0, "band": ((43.5 - 15.0) / 60.0, (46.5 - 15.0) / 60.0),
    "episode_s": 900.0, "settle_s": 300.0,
    "disturbance_at_s": 400.0, "disturbance_episode_s": 1200.0,
    "max_experiments": 8, "min_experiments_before_generate": 3,
    "max_single_experiment_s": 180.0, "after_change_max_single_experiment_s": 300.0,
    "worst_case_rate_per_unit_u": 0.006,
    "soft_high_limit": 0.85, "hard_cutoff": 0.90,
    "monitor_window_s": 60.0, "monitor_hold_s": 30.0, "monitor_factor": 2.0, "monitor_floor": 0.02,
    "monitor_calibrate_s": 380.0, "monitor_pre_s": 400.0, "monitor_duration_s": 1500.0, "monitor_post_detection_s": 200.0,
    "y_unit": "°C", "y_scale": 60.0, "y_offset": 15.0,
}
TCLAB_SIM = PlantProfile(name="tclab_sim", description_for_operator="APMonitor TCLab simulator (TCLabModel), accelerated.", **_TCLAB_COMMON)
TCLAB = PlantProfile(name="tclab", description_for_operator="Physical TCLab heater board over USB serial.", **_TCLAB_COMMON)

PROFILES: dict[str, PlantProfile] = {p.name: p for p in (TANK, TCLAB_SIM, TCLAB)}


def get_profile(name: str) -> PlantProfile:
    try:
        return PROFILES[name]
    except KeyError as e:
        raise ValueError(f"unknown plant profile {name!r}; choose from {sorted(PROFILES)}") from e
