"""Run session state: everything the orchestrator knows about one run.

Trusted. The agent never sees a Session; it sees ``backend.agent.view.build_agent_view(session)``.
"""
from __future__ import annotations

import time
from typing import Any, Literal

from pydantic import BaseModel, Field

from backend.agent.contracts import ControllerSubmission, Hypothesis, RevisionSubmission
from backend.evaluation.report import EvaluationReport
from backend.schemas import Observation, ProposalVerdict, Trace

Stage = Literal[
    "NEW", "EXPLORING", "HYPOTHESIZING", "GENERATING", "STATIC_CHECK", "SANDBOX_CHECK", "EVALUATING",
    "REVISING", "DEPLOYABLE", "MONITORING", "ADAPTING", "COMPLETE", "FAILED", "STOPPED",
]


class Budget(BaseModel):
    max_experiments: int = 12
    max_candidates: int = 5
    max_model_calls: int = 40
    max_wall_clock_s: float = 30 * 60  # measured: Spark run ~7 min exploring + 2 min authoring + eval + monitoring
    min_experiments_before_generate: int = 3
    max_reidentification_experiments: int = 4  # bounded experiments on the changed machine before revising
    max_contract_fix_attempts: int = 2  # static/sandbox-load failures per candidate slot


class Objective(BaseModel):
    target: float = 0.60
    band: tuple[float, float] = (0.55, 0.65)
    settle_s: float = 30.0


class PublicConstraints(BaseModel):
    """What the agent is told about the safety policy. Values, not mechanisms."""

    u_range: tuple[float, float] = (0.0, 1.0)
    soft_high_limit: float = 0.85
    hard_cutoff: float = 0.90
    max_single_experiment_s: float = 20.0
    after_change_max_single_experiment_s: float = 40.0  # longer holds so a long delay fits in one experiment
    worst_case_rate_per_unit_u: float = 0.08


class ExperimentRecord(BaseModel):
    id: str
    phase: Literal["discovery", "after_change"] = "discovery"
    u_before: float | None = None  # command applied immediately before this experiment started (agent's own action)
    t_since_last_command_change_s: float | None = None  # at experiment start; 0 if this experiment changed the command
    proposal: dict[str, Any]  # ExperimentProposal.model_dump()
    verdict: ProposalVerdict
    status: Literal["completed", "rejected", "invalid"]
    t_start: float | None = None
    trace: Trace | None = None  # TRUSTED (has h_true)


class CandidateRecord(BaseModel):
    candidate_id: str
    version: int
    parent_id: str | None
    model_id: str
    prompt_hash: str
    submission_kind: Literal["controller", "revision", "fix"]
    submission: dict[str, Any]  # ControllerSubmission / RevisionSubmission dump (includes source)
    static_ok: bool | None = None
    static_violations: list[str] = Field(default_factory=list)
    sandbox_ok: bool | None = None
    sandbox_detail: list[str] = Field(default_factory=list)
    evaluation: EvaluationReport | None = None  # TRUSTED
    disturbance_evaluation: EvaluationReport | None = None  # TRUSTED
    status: Literal["registered", "rejected_static", "rejected_sandbox", "evaluated", "approved", "failed_gate"] = "registered"


class MonitoringState(BaseModel):
    deployed_candidate_id: str | None = None
    baseline_window_mae: float | None = None
    recent_window_mae: float | None = None
    degraded: bool = False
    degraded_at_t: float | None = None
    pre_trace: Trace | None = None  # TRUSTED
    post_trace: Trace | None = None  # TRUSTED
    disturbance_family: str | None = None  # TRUSTED: never to the agent
    disturbance_at_t: float | None = None  # TRUSTED


class Session(BaseModel):
    run_id: str
    plant_description: str
    objective: Objective = Field(default_factory=Objective)
    constraints: PublicConstraints = Field(default_factory=PublicConstraints)
    budget: Budget = Field(default_factory=Budget)
    agent_mode: Literal["live", "mock", "replay"] = "live"
    model_id: str = ""
    stage: Stage = "NEW"
    stage_history: list[dict[str, Any]] = Field(default_factory=list)
    started_at: float = Field(default_factory=time.time)
    current_obs: Observation | None = None
    experiments: list[ExperimentRecord] = Field(default_factory=list)
    ledger: list[Hypothesis] = Field(default_factory=list)
    ledger_history: list[dict[str, Any]] = Field(default_factory=list)
    candidates: list[CandidateRecord] = Field(default_factory=list)
    monitoring: MonitoringState = Field(default_factory=MonitoringState)
    model_calls: int = 0
    stop_requested: bool = False

    # --------------------------------------------------------------- helpers
    def transition(self, stage: Stage, **info: Any) -> dict[str, Any]:
        rec = {"from": self.stage, "to": stage, "ts": time.time(), **info}
        self.stage = stage
        self.stage_history.append(rec)
        return rec

    def completed_experiments(self) -> list[ExperimentRecord]:
        return [e for e in self.experiments if e.status == "completed" and e.phase == "discovery"]

    def experiments_remaining(self) -> int:
        n = len([e for e in self.experiments if e.phase == "discovery"])
        return max(0, self.budget.max_experiments - n)

    def reidentification_remaining(self) -> int:
        n = len([e for e in self.experiments if e.phase == "after_change"])
        return max(0, self.budget.max_reidentification_experiments - n)

    def candidates_remaining(self) -> int:
        return max(0, self.budget.max_candidates - len(self.candidates))

    def elapsed_s(self) -> float:
        return time.time() - self.started_at

    def wall_clock_remaining_s(self) -> float:
        return max(0.0, self.budget.max_wall_clock_s - self.elapsed_s())

    def may_generate(self) -> tuple[bool, str]:
        n = len(self.completed_experiments())
        if n < self.budget.min_experiments_before_generate:
            return False, f"only {n} completed experiments; minimum is {self.budget.min_experiments_before_generate}"
        return True, "ok"

    def latest_candidate(self) -> CandidateRecord | None:
        return self.candidates[-1] if self.candidates else None

    def approved_candidate(self) -> CandidateRecord | None:
        for c in reversed(self.candidates):
            if c.status == "approved":
                return c
        return None

    def record_ledger(self, hypotheses: list[Hypothesis], after_experiment: str | None) -> None:
        self.ledger = list(hypotheses)
        self.ledger_history.append(
            {"after_experiment": after_experiment, "ts": time.time(), "hypotheses": [h.model_dump() for h in hypotheses]}
        )


def submission_source(sub: ControllerSubmission | RevisionSubmission | dict[str, Any]) -> str:
    if isinstance(sub, dict):
        return str(sub["source_code"])
    return sub.source_code
