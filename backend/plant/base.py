"""PlantAdapter: the trusted interface every plant (simulated or real) implements."""
from __future__ import annotations

from abc import ABC, abstractmethod

from backend.schemas import DisturbanceSpec, Observation


class PlantAdapter(ABC):
    """Abstract plant.

    The supervisor sits between any controller and `step()`; `step()` receives an
    already-supervised input but still validates it (defense in depth).

    #####################################################################################
    # TRUST BOUNDARY: `true_state()` and any `hidden_params()` on subclasses are TRUSTED  #
    # ONLY. They exist for scoring and audit logs. Their output must NEVER reach the     #
    # agent view, prompts, or anything model-facing.                                    #
    #####################################################################################
    """

    @property
    @abstractmethod
    def dt(self) -> float:
        """Fixed integration / control step in simulated seconds."""

    @abstractmethod
    def reset(self, seed: int, scenario: int | None = None) -> Observation:
        """Re-initialise deterministically; clears disturbances.

        `seed` selects the machine (hidden physical parameters). `scenario` (default: `seed`)
        selects episode-specific conditions: initial state, noise stream, disturbance magnitudes.
        """

    @abstractmethod
    def observe(self) -> Observation:
        """Return the latest noisy measurement without advancing time."""

    @abstractmethod
    def step(self, u_applied: float) -> Observation:
        """Advance one `dt` with the given input. Raise ValueError on non-finite or out-of-[0,1] input."""

    @abstractmethod
    def true_state(self) -> dict:
        """TRUSTED ONLY: {"h_true": float, "t": float}. Must never reach the agent view."""

    @abstractmethod
    def public_description(self) -> str:
        """Short domain description with NO parameters; safe for the agent."""

    @abstractmethod
    def schedule_disturbance(self, spec: DisturbanceSpec) -> None:
        """Schedule a hidden plant change (trusted operator/evaluator only)."""

    @abstractmethod
    def emergency_stop(self) -> None:
        """Immediately set the internal actuator to 0."""
