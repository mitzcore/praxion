"""Agent I/O contracts: the only shapes Muse may return at each stage.

These Pydantic models are mirrored to strict JSON schemas (``additionalProperties: false``
on every object, every property required) for Meta's constrained decoding. A schema-valid
answer is NOT a safe answer: the orchestrator re-validates every numeric field against the
trusted limits before anything touches the plant.
"""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

DiagnosisCategory = Literal[
    "actuator_weaker",  # same command now produces a smaller rise
    "outflow_increased",  # level falls faster at a given command
    "response_slower",  # longer lag or delay between command and response
    "sensor_changed",  # measurement noise or behaviour changed
    "unknown",
]


class Hypothesis(BaseModel):
    id: str = Field(description="Short stable id such as H1, H2. Keep ids stable across revisions.")
    statement: str = Field(description="A falsifiable statement about how the system responds.")
    confidence: float = Field(description="0..1 belief after considering all evidence so far.")
    evidence_refs: list[str] = Field(description="Experiment ids that support or weaken this hypothesis.")


class ExperimentProposal(BaseModel):
    """Stage EXPLORING: Muse revises its ledger and proposes one bounded experiment."""

    hypotheses: list[Hypothesis] = Field(description="The complete current ledger, revised.")
    uncertainty_targeted: str = Field(description="Which uncertainty this experiment reduces and why it matters for control.")
    command_u: float = Field(description="Constant input to apply, within the allowed range.")
    duration_s: float = Field(description="Seconds to hold the command; must respect the maximum experiment duration.")
    safety_argument: str = Field(description="Why the worst-case level stays below the soft limit.")
    expected_observation: str = Field(description="What you expect to see if your leading hypothesis is right.")
    ready_to_generate: bool = Field(description="True only when the evidence justifies designing a controller.")
    readiness_justification: str = Field(description="Which uncertainties are resolved well enough, and which remain and why they are acceptable.")
    operator_note: str = Field(description="One plain-English sentence for the operator timeline.")


class ControllerSubmission(BaseModel):
    """Stage GENERATING: Muse authors a complete controller module."""

    machine_card: str = Field(description="Plain-language summary of what you learned about this machine: response direction, speed, lag, dead zone, self-draining, noise. Numbers where you have them.")
    design_rationale: str = Field(description="Why this control structure and these constants follow from the evidence.")
    source_code: str = Field(description="Complete Python module defining control(obs, state). Only `import math` is allowed.")
    predicted_behavior: str = Field(description="How you expect the closed loop to behave: settling time, overshoot, steady-state duty.")
    self_test_expectations: list[str] = Field(description="Concrete checks the evaluator should see pass.")
    operator_note: str


class RevisionSubmission(BaseModel):
    """Stage REVISING / ADAPTING: Muse diagnoses measured failure and authors a revised module."""

    diagnosis: str = Field(description="Causal explanation of the measured degradation, grounded in the traces.")
    diagnosis_category: DiagnosisCategory = Field(description="Your best single classification of what changed in the machine.")
    change_summary: str = Field(description="What changed in the code and why it addresses the diagnosis.")
    machine_card: str
    design_rationale: str
    source_code: str
    predicted_behavior: str
    self_test_expectations: list[str]
    operator_note: str


def strict_schema(model: type[BaseModel]) -> dict[str, Any]:
    """Pydantic JSON schema with every object closed and every property required (Meta strict mode)."""
    schema = model.model_json_schema()

    def walk(node: Any) -> None:
        if isinstance(node, dict):
            if node.get("type") == "object" and "properties" in node:
                node["additionalProperties"] = False
                node["required"] = list(node["properties"].keys())
            for v in node.values():
                walk(v)
        elif isinstance(node, list):
            for v in node:
                walk(v)

    walk(schema)
    return schema


def response_format(model: type[BaseModel]) -> dict[str, Any]:
    """Chat Completions ``response_format`` payload for a contract model."""
    return {
        "type": "json_schema",
        "json_schema": {"name": model.__name__.lower(), "schema": strict_schema(model), "strict": True},
    }
