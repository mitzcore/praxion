"""MOCK agent for CI only. Spends no credits. Produces deterministic, clearly labeled output.

Every artifact produced through this agent carries model_id "MOCK-NOT-MUSE". It exists to
exercise the orchestrator, registry, sandbox, evaluator, and UI plumbing. It must never be
presented as model output, and the UI must show a MOCK badge whenever it is in use.
"""
from __future__ import annotations

from typing import Any, TypeVar

from pydantic import BaseModel

from backend.agent.contracts import ControllerSubmission, ExperimentProposal, Hypothesis, RevisionSubmission
from backend.agent.muse_client import CallRecord, UsageTotals

T = TypeVar("T", bound=BaseModel)

MOCK_MODEL_ID = "MOCK-NOT-MUSE"

# Deliberately plain and labeled. Not tuned to the simulator; it is plumbing, not a result.
_MOCK_V1 = '''# MOCK CONTROLLER (CI plumbing only; not model-authored)
import math

def control(obs, state):
    y = obs["y"]
    target = obs["target"]
    dt = obs["dt"] if obs["dt"] > 0 else 0.1
    if not math.isfinite(y):
        return 0.0, state
    err = target - y
    integ = state.get("integ", 0.0) + err * dt
    integ = max(-2.0, min(2.0, integ))
    u = 0.5 + 2.5 * err + 0.2 * integ
    u = max(0.0, min(1.0, u))
    return u, {"integ": integ}
'''

_MOCK_V2 = _MOCK_V1.replace("u = 0.5 + 2.5 * err + 0.2 * integ", "u = 0.55 + 3.0 * err + 0.35 * integ").replace(
    "# MOCK CONTROLLER (CI plumbing only; not model-authored)",
    "# MOCK CONTROLLER v2 (CI plumbing only; not model-authored)",
)


class MockMuseClient:
    """Drop-in for MuseClient.structured() with canned answers."""

    model = MOCK_MODEL_ID

    def __init__(self) -> None:
        self.totals = UsageTotals()
        self.records: list[CallRecord] = []
        self._n_proposals = 0
        self._n_reid = 0

    def structured(self, stage: str, messages: list[dict[str, str]], contract: type[T]) -> tuple[T, CallRecord]:
        rec = CallRecord(stage=stage, model=MOCK_MODEL_ID, attempt=1, ok=True, latency_s=0.0)
        self.records.append(rec)
        self.totals.calls += 1
        return self._answer(contract, stage), rec  # type: ignore[return-value]

    def _answer(self, contract: type[BaseModel], stage: str = "") -> BaseModel:
        if contract is ExperimentProposal and stage == "reidentifying":
            # Two fixed experiments on the changed machine, then ready to revise (exercises the changed-twin path).
            self._n_reid += 1
            return ExperimentProposal(
                hypotheses=[Hypothesis(id="C1", statement="MOCK: machine changed", confidence=0.5, evidence_refs=[])],
                uncertainty_targeted="MOCK", command_u=[0.0, 0.6][(self._n_reid - 1) % 2], duration_s=30.0,
                safety_argument="MOCK: bounded", expected_observation="MOCK", ready_to_generate=self._n_reid > 2,
                readiness_justification="MOCK: fixed schedule", operator_note="MOCK after-change probe (CI only)",
            )
        if contract is ExperimentProposal:
            self._n_proposals += 1
            u = [0.4, 0.7, 0.0, 0.55][(self._n_proposals - 1) % 4]
            return ExperimentProposal(
                hypotheses=[Hypothesis(id="H1", statement="MOCK: u raises y", confidence=0.5, evidence_refs=[])],
                uncertainty_targeted="MOCK",
                command_u=u,
                duration_s=8.0,
                safety_argument="MOCK: bounded",
                expected_observation="MOCK",
                ready_to_generate=self._n_proposals >= 4,
                readiness_justification="MOCK: fixed schedule",
                operator_note="MOCK proposal (CI only)",
            )
        if contract is ControllerSubmission:
            return ControllerSubmission(
                machine_card="MOCK machine card", design_rationale="MOCK", source_code=_MOCK_V1,
                predicted_behavior="MOCK", self_test_expectations=["MOCK"], operator_note="MOCK controller (CI only)",
            )
        if contract is RevisionSubmission:
            return RevisionSubmission(
                diagnosis="MOCK", diagnosis_category="unknown", change_summary="MOCK: gains changed",
                machine_card="MOCK", design_rationale="MOCK", source_code=_MOCK_V2, predicted_behavior="MOCK",
                self_test_expectations=["MOCK"], operator_note="MOCK revision (CI only)",
            )
        raise TypeError(f"MockMuseClient has no canned answer for {contract.__name__}")


def mock_payload(x: Any) -> Any:  # small helper for tests
    return x
