"""The orchestrator: trusted finite-state loop that drives Muse through discovery, authoring,
validation, evaluation, deployment, monitoring and repair.

Trust boundary. The model only ever receives ``build_agent_view(session)`` (snapshotted), plus
its own previous source and agent-safe feedback strings. Every numeric decision the model
returns is re-validated here or by the Supervisor before anything touches the plant.
"""
from __future__ import annotations

import contextlib
import json
import logging
import math
import sys
import threading
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any, Protocol

from pydantic import BaseModel

from backend.agent.contracts import ControllerSubmission, ExperimentProposal, RevisionSubmission
from backend.agent.muse_client import CallRecord, MuseError
from backend.agent.prompts import (
    PROMPT_HASH,
    PROMPT_VERSION,
    authoring_messages,
    discovery_messages,
    fix_messages,
    reidentify_messages,
    revision_messages,
)
from backend.agent.session import CandidateRecord, ExperimentRecord, Session
from backend.agent.view import build_agent_view, find_leaks
from backend.controller.interface_tests import run_interface_tests
from backend.controller.protocol import Controller
from backend.controller.registry import Registry
from backend.controller.runtime import run_constant_input
from backend.controller.sandbox import SandboxError, make_sandbox
from backend.controller.static_check import static_check
from backend.evaluation import suite as evalsuite
from backend.evaluation.monitor import DegradationDetector, run_monitored_rollout
from backend.evaluation.report import EvaluationReport
from backend.plant.base import PlantAdapter
from backend.profiles import TANK, PlantProfile
from backend.safety.supervisor import Supervisor
from backend.schemas import DisturbanceSpec
from backend.storage.artifacts import RunStore

log = logging.getLogger(__name__)

class AgentLike(Protocol):
    model: str

    def structured(self, stage: str, messages: list[dict[str, str]], contract: type[Any]) -> tuple[Any, CallRecord]: ...


class OrchestratorConfig(BaseModel):
    model_config = {"arbitrary_types_allowed": True}
    plant_seed: int = 1  # TRUSTED. Never in the agent view.
    sandbox_mode: str = "docker"
    profile: PlantProfile = TANK
    # Evaluator plant. None → the evaluator instantiates the default simulator (TankSimulator) for the
    # profile; a callable → used as plant_factory; "twin" → a ThermalTwin is fitted by trusted code from
    # the discovery experiments after exploration and used for every gate (physical-plant path).
    eval_plant_factory: Any = None
    # Physical plants: the operator applies the disturbance by hand when prompted; nothing is scheduled.
    operator_disturbance: bool = False
    # TRUSTED. Magnitude handed to the plant's schedule_disturbance (physical plants with a trusted actuator
    # fault: pump_derate fraction). None → the plant's own default. Never in the agent view.
    disturbance_magnitude: float | None = None
    max_adaptation_attempts: int = 3

    @property
    def monitor_calibrate_s(self) -> float:
        return self.profile.monitor_calibrate_s

    @property
    def monitor_pre_s(self) -> float:
        return self.profile.monitor_pre_s

    @property
    def monitor_duration_s(self) -> float:
        return self.profile.monitor_duration_s

    @property
    def monitor_post_detection_s(self) -> float:
        return self.profile.monitor_post_detection_s


EventHook = Callable[[dict[str, Any]], None]


class Orchestrator:
    def __init__(
        self,
        session: Session,
        store: RunStore,
        agent: AgentLike,
        plant: PlantAdapter,
        supervisor: Supervisor,
        registry: Registry | None = None,
        config: OrchestratorConfig | None = None,
        on_event: EventHook | None = None,
    ) -> None:
        self.s = session
        self.store = store
        self.agent = agent
        self.plant = plant
        self.sup = supervisor
        # Registry stores under <root>/runs/<run_id>; the store's dir is <root>/runs/<run_id>.
        self.registry = registry or Registry(store.dir.parent.parent)
        self.cfg = config or OrchestratorConfig()
        self.on_event = on_event
        self._view_index = 0
        self._last_u: float = 0.0
        self._last_u_change_t: float = 0.0
        self.s.model_id = getattr(agent, "model", "?")

    # ================================================================== events
    def _event(self, kind: str, **payload: Any) -> None:
        rec = self.store.event(kind, stage=self.s.stage, **payload)
        if self.on_event:
            self.on_event(rec)

    def _transition(self, stage: str, **info: Any) -> None:
        rec = self.s.transition(stage, **info)  # type: ignore[arg-type]
        self._event("stage", **rec)

    def _check_budget(self) -> None:
        if self.s.stop_requested:
            raise _Stop("operator stop")
        if self.s.wall_clock_remaining_s() <= 0:
            raise _Stop("wall clock budget exhausted")

    # ============================================================ model calls
    def _ask(self, stage: str, messages: list[dict[str, str]], contract: type[Any], view: dict[str, Any]) -> Any:
        # The view is scanned, and so is the full message list: feedback text and gate reasons are built
        # outside the view. The run id is a secret because the operator's label and the plant seed are in it.
        # The model's own controller source is shown back to it for revision and is exempt (it may
        # legitimately contain any identifier it chose); everything else in the messages is scanned.
        secrets = (self.s.run_id,)
        scan_text = json.dumps(messages, ensure_ascii=False)
        for c in self.s.candidates:
            with contextlib.suppress(Exception):  # a missing source is not a leak
                scan_text = scan_text.replace(json.dumps(self._source(c), ensure_ascii=False)[1:-1], "")
        leaks = find_leaks(view, secrets=secrets) + find_leaks({"messages": scan_text}, secrets=secrets)
        if leaks:  # defense in depth: never send a leaking view
            self._event("error", error="agent view leak blocked", leaks=leaks)
            raise _Stop("agent view leak blocked")
        self._view_index += 1
        self.store.snapshot_view(stage, self._view_index, view)
        parsed, rec = self.agent.structured(stage, messages, contract)
        self.s.model_calls += 1
        self._event(
            "model_call", call_stage=stage, model=rec.model, ok=rec.ok, latency_s=round(rec.latency_s, 2),
            prompt_tokens=rec.prompt_tokens, completion_tokens=rec.completion_tokens,
            reasoning_tokens=rec.reasoning_tokens, cost_usd=round(rec.cost_usd, 5),
        )
        return parsed

    # ============================================================== discovery
    def run_discovery(self) -> Session:
        """NEW → EXPLORING → GENERATING → checks → EVALUATING → DEPLOYABLE | FAILED."""
        try:
            self.plant.reset(self.cfg.plant_seed)
            self.s.current_obs = self.plant.observe()
            self._event("run_started", model=self.s.model_id, prompt_version=PROMPT_VERSION, prompt_hash=PROMPT_HASH,
                        agent_mode=self.s.agent_mode, sandbox_mode=self.cfg.sandbox_mode,
                        profile=self._profile_summary())
            self._transition("EXPLORING")
            self._explore()
            self._idle_physical_plant("after discovery")
            self._prepare_eval_plant()
            self._transition("GENERATING")
            approved = self._author_until_approved()
            if approved is None:
                self._transition("FAILED", reason="no candidate passed the release gate within budget")
            else:
                self._transition("DEPLOYABLE", candidate_id=approved.candidate_id)
        except _Stop as e:
            self._transition("STOPPED", reason=str(e))
        except MuseError as e:
            self._event("error", error=f"model: {e}")
            self._transition("FAILED", reason=f"model error: {e}")
        except Exception as e:
            log.exception("unexpected error during discovery")
            self._event("error", error=f"unexpected: {type(e).__name__}: {e}")
            self._transition("FAILED", reason=f"unexpected error: {type(e).__name__}: {e}")
        finally:
            self._persist_summary()
        return self.s

    def _prepare_eval_plant(self) -> None:
        """Physical-plant path: fit a trusted digital twin from the discovery experiments and use it
        for every hidden-scenario gate. The twin parameters never enter the agent view."""
        if self.cfg.eval_plant_factory != "twin":
            return
        from backend.plant.thermal_twin import fit_twin, twin_factory

        traces = [e.trace for e in self.s.experiments if e.trace is not None and e.status == "completed"]
        params = fit_twin(traces, dt=self.plant.dt)
        report = getattr(params, "report", None)
        self._eval_plant_factory = twin_factory(params)
        self.store.write_json("twin_fit.json", params.model_dump(mode="json") if hasattr(params, "model_dump") else str(params))
        self._event("twin_fitted", n_traces=len(traces),
                    report=report.model_dump(mode="json") if hasattr(report, "model_dump") else report)

    def _eval_factory(self) -> Any:
        f = getattr(self, "_eval_plant_factory", None)
        if f is not None:
            return f
        return self.cfg.eval_plant_factory if callable(self.cfg.eval_plant_factory) else None

    def _explore(self) -> None:
        while self.s.experiments_remaining() > 0:
            self._check_budget()
            self.s.current_obs = self.plant.observe()
            view = build_agent_view(self.s)
            proposal: ExperimentProposal = self._ask("exploring", discovery_messages(view), ExperimentProposal, view)
            self.s.record_ledger(proposal.hypotheses, after_experiment=self.s.experiments[-1].id if self.s.experiments else None)
            self._event("ledger", hypotheses=[h.model_dump() for h in proposal.hypotheses],
                        operator_note=proposal.operator_note)
            if proposal.ready_to_generate:
                allowed, why = self.s.may_generate()
                if allowed:
                    self._event("ready_to_generate", justification=proposal.readiness_justification)
                    return
                self._event("readiness_refused", reason=why, justification=proposal.readiness_justification)
            self._run_experiment(proposal)
        self._event("exploration_budget_exhausted")

    def _run_experiment(self, proposal: ExperimentProposal, phase: str = "discovery") -> None:
        exp_id = f"E{len(self.s.experiments) + 1}"
        obs = self.plant.observe()
        if phase == "after_change":
            lim = self.sup.limits.model_copy(update={"max_single_experiment_s": self.s.constraints.after_change_max_single_experiment_s})
            verdict = Supervisor(lim).validate_proposal(proposal.command_u, proposal.duration_s, obs, dt=self.plant.dt)
        else:
            verdict = self.sup.validate_proposal(proposal.command_u, proposal.duration_s, obs, dt=self.plant.dt)
        u_before = self._last_u
        since_change = 0.0 if (verdict.ok and abs(float(proposal.command_u) - self._last_u) > 1e-9) else max(0.0, obs.t - self._last_u_change_t)
        self._event("experiment_proposed", experiment_id=exp_id, phase=phase, command_u=proposal.command_u,
                    duration_s=proposal.duration_s, uncertainty=proposal.uncertainty_targeted,
                    expected=proposal.expected_observation, safety_argument=proposal.safety_argument,
                    verdict_ok=verdict.ok, verdict=verdict.reason, operator_note=proposal.operator_note)
        if not verdict.ok:
            self.s.experiments.append(ExperimentRecord(id=exp_id, phase=phase, proposal=proposal.model_dump(),  # type: ignore[arg-type]
                                                       verdict=verdict, status="rejected", u_before=u_before))
            return
        self.sup.reset_counters()
        if abs(float(verdict.u) - self._last_u) > 1e-9:
            self._last_u_change_t = obs.t
        trace = run_constant_input(self.plant, self.sup, float(verdict.u), float(verdict.duration_s), self.s.objective.target)
        if trace.steps:
            self._last_u = float(trace.steps[-1].u_applied)
        hard = any(s.reason.startswith("hard_cutoff") for s in trace.steps)
        status = "invalid" if hard else "completed"
        if hard:
            self.plant.emergency_stop()
        self.s.experiments.append(ExperimentRecord(id=exp_id, phase=phase, proposal=proposal.model_dump(),  # type: ignore[arg-type]
                                                   verdict=verdict, status=status, u_before=u_before,
                                                   t_since_last_command_change_s=round(since_change, 1),
                                                   t_start=trace.steps[0].t if trace.steps else None, trace=trace))
        self.s.current_obs = self.plant.observe()
        self._event("experiment_result", experiment_id=exp_id, phase=phase, status=status, n_samples=len(trace.steps),
                    y_start=trace.steps[0].y if trace.steps else None, y_end=trace.steps[-1].y if trace.steps else None,
                    overrides=self.sup.override_count, samples=trace.agent_safe(60))
        self.store.write_json("experiments.json", [e.model_dump(exclude={"trace"}) | {"samples": (e.trace.agent_safe(60) if e.trace else [])}
                                                   for e in self.s.experiments])

    # ============================================================== authoring
    def _author_until_approved(self) -> CandidateRecord | None:
        parent: CandidateRecord | None = None
        while self.s.candidates_remaining() > 0:
            self._check_budget()
            view = build_agent_view(self.s)
            if parent is None:
                sub = self._ask("authoring", authoring_messages(view), ControllerSubmission, view)
                kind = "controller"
            else:
                feedback = self._feedback_for(parent)
                sub = self._ask("revising", revision_messages(view, self._source(parent), feedback), RevisionSubmission, view)
                kind = "revision"
            cand = self._register(sub, parent, kind)
            cand = self._validate_contract(cand, view)
            if cand.status.startswith("rejected"):
                parent = cand
                continue
            self._transition("EVALUATING", candidate_id=cand.candidate_id)
            report = self._evaluate_heldout(cand)
            if report.gate_passed:
                cand.status = "approved"
                self._event("candidate_approved", candidate_id=cand.candidate_id, aggregate=report.aggregate)
                return cand
            cand.status = "failed_gate"
            self._event("candidate_failed_gate", candidate_id=cand.candidate_id, reasons=report.gate_reasons,
                        aggregate=report.aggregate)
            self._transition("REVISING", candidate_id=cand.candidate_id)
            parent = cand
        return None

    def _register(self, sub: ControllerSubmission | RevisionSubmission, parent: CandidateRecord | None, kind: str) -> CandidateRecord:
        rationale = sub.design_rationale if kind == "controller" else getattr(sub, "change_summary", sub.design_rationale)
        c = self.registry.persist(sub.source_code, run_id=self.s.run_id, parent_id=parent.candidate_id if parent else None,
                                  model_id=self.s.model_id, prompt_hash=PROMPT_HASH, rationale=rationale,
                                  extra={"kind": kind, "machine_card": sub.machine_card,
                                         "predicted_behavior": sub.predicted_behavior,
                                         "diagnosis": getattr(sub, "diagnosis", None),
                                         "diagnosis_category": getattr(sub, "diagnosis_category", None)})
        assert Path(c.path).read_bytes() == sub.source_code.encode("utf-8"), "registry bytes differ from model output"
        rec = CandidateRecord(candidate_id=c.id, version=c.version, parent_id=c.parent_id, model_id=c.model_id,
                              prompt_hash=c.prompt_hash, submission_kind=kind, submission=sub.model_dump())  # type: ignore[arg-type]
        self.s.candidates.append(rec)
        self.store.write_text(f"machine_card_v{c.version}.md", sub.machine_card)
        self._event("candidate_registered", candidate_id=c.id, version=c.version, parent_id=c.parent_id, sha256=c.sha256,
                    byte_length=c.byte_length, submission_kind=kind, operator_note=sub.operator_note,
                    diagnosis_category=getattr(sub, "diagnosis_category", None))
        if c.parent_id:
            self.store.write_text(f"controller_diff_v{self.registry.parse_id(c.parent_id)[1]}_v{c.version}.patch",
                                  self.registry.diff(c.parent_id, c.id))
        return rec

    def _validate_contract(self, cand: CandidateRecord, view: dict[str, Any]) -> CandidateRecord:
        """Static check then sandbox interface tests. Contract failures get bounded fix attempts
        that do not consume candidate slots beyond max_contract_fix_attempts."""
        for attempt in range(self.cfg_fix_attempts() + 1):
            self._transition("STATIC_CHECK", candidate_id=cand.candidate_id)
            sc = static_check(self._source(cand))
            cand.static_ok, cand.static_violations = sc.ok, list(sc.violations)
            self._event("static_check", candidate_id=cand.candidate_id, ok=sc.ok, violations=sc.violations)
            if sc.ok:
                self._transition("SANDBOX_CHECK", candidate_id=cand.candidate_id)
                ok, detail = self._sandbox_interface(cand)
                cand.sandbox_ok, cand.sandbox_detail = ok, detail
                self._event("sandbox_check", candidate_id=cand.candidate_id, ok=ok, detail=detail)
                if ok:
                    return cand
                cand.status = "rejected_sandbox"
                violations = detail
            else:
                cand.status = "rejected_static"
                violations = sc.violations
            if attempt >= self.cfg_fix_attempts() or self.s.candidates_remaining() <= 0:
                return cand
            self._check_budget()
            fix = self._ask("fixing", fix_messages(view, self._source(cand), violations), RevisionSubmission, view)
            cand = self._register(fix, cand, "fix")
        return cand

    def cfg_fix_attempts(self) -> int:
        return self.s.budget.max_contract_fix_attempts

    def _sandbox_interface(self, cand: CandidateRecord) -> tuple[bool, list[str]]:
        try:
            report = run_interface_tests(lambda: self._make_controller(cand))
        except SandboxError as e:
            return False, [f"sandbox: {type(e).__name__}: {e}"]
        detail = [f"{c.name}: {'ok' if c.ok else 'FAIL'} {c.detail}" for c in report.checks]
        return report.ok, detail

    def _make_controller(self, cand: CandidateRecord) -> Controller:
        return make_sandbox(self._source(cand), name=cand.candidate_id, mode=self.cfg.sandbox_mode)

    def _source(self, cand: CandidateRecord) -> str:
        return self.registry.load_source(cand.candidate_id)

    def _scrub(self, text: str) -> str:
        """Replace the run id (operator label, plant seed) in trusted feedback text with the opaque form."""
        return text.replace(self.s.run_id + "-v", "v").replace(self.s.run_id, "this run")

    def _feedback_for(self, cand: CandidateRecord) -> str:
        return self._scrub(self._feedback_for_raw(cand))

    def _feedback_for_raw(self, cand: CandidateRecord) -> str:
        if cand.status == "rejected_static":
            return "Static check rejected the module:\n- " + "\n- ".join(cand.static_violations)
        if cand.status == "rejected_sandbox":
            return "Sandbox interface tests failed:\n- " + "\n- ".join(cand.sandbox_detail)
        if cand.evaluation is not None:
            rep = cand.evaluation.agent_safe(include_traces=False, band=self.s.objective.band)
            lines = ["The independent evaluator did not pass the release gate.",
                     f"Gate reasons: {rep['gate_reasons']}", f"Aggregate: {rep['aggregate']}",
                     "Measured facts per hidden episode (from the noisy measurement and the applied command):"]
            for ep in rep["episodes"]:
                ms = ep.get("measured_summary", {})
                lines.append(f"  episode {ep['index']}: y_start={ms.get('y_start')} y_end={ms.get('y_end')} "
                             f"y_mean_last_30s={ms.get('y_mean_last_30s')} u_mean_last_30s={ms.get('u_mean_last_30s')} "
                             f"slope_last_30s={ms.get('y_slope_last_30s_per_s')}/s in_band_last_30s={ms.get('measured_in_band_fraction_last_30s')}; "
                             f"fail: {ep['fail_reasons']}")
            lines.append("Full traces are in the session view under candidates[].evaluation.")
            return "\n".join(lines)
        return "No feedback recorded."

    # ============================================================= evaluation
    def _evaluate_heldout(self, cand: CandidateRecord) -> EvaluationReport:
        kw: dict[str, Any] = {"profile": self.cfg.profile}
        if self._eval_factory() is not None:
            kw["plant_factory"] = self._eval_factory()
        report = evalsuite.evaluate_heldout(lambda: self._make_controller(cand), candidate_id=cand.candidate_id,
                                            plant_seed=self.cfg.plant_seed, limits=self.sup.limits, **kw)
        cand.evaluation = report
        cand.status = "evaluated"
        self.store.write_json(f"evaluation_v{cand.version}.json", report.model_dump(mode="json"))
        self._event("evaluation", candidate_id=cand.candidate_id, suite=report.suite, gate=report.gate_name,
                    gate_passed=report.gate_passed, reasons=report.gate_reasons, aggregate=report.aggregate,
                    episodes=[{"index": e.index, "passed": e.passed, "mae": e.metrics.mae,
                               "in_band": e.metrics.in_band_fraction, "overrides": e.metrics.override_count,
                               "violations": e.metrics.hard_violations} for e in report.episodes])
        return report

    # ============================================= monitoring and self-repair
    def run_monitoring(self, disturbance_family: str | None) -> Session:
        """DEPLOYABLE → MONITORING → (ADAPTING → EVALUATING)* → COMPLETE | FAILED.

        The disturbance family is known to the operator and the evaluator only. The agent sees
        traces and scores."""
        deployed = self.s.approved_candidate()
        if deployed is None:
            self._transition("FAILED", reason="nothing deployed")
            return self.s
        try:
            self._transition("MONITORING", candidate_id=deployed.candidate_id)
            m = self.s.monitoring
            m.deployed_candidate_id = deployed.candidate_id
            m.disturbance_family = disturbance_family
            m.disturbance_at_t = self.cfg.monitor_pre_s if disturbance_family else None
            if self.cfg.operator_disturbance:
                spec = None  # the operator applies it by hand when prompted at monitor_pre_s
            else:
                spec = (DisturbanceSpec(family=disturbance_family, at_t=self.cfg.monitor_pre_s,  # type: ignore[arg-type]
                                        magnitude=self.cfg.disturbance_magnitude)
                        if disturbance_family else None)
            self._event("disturbance_scheduled", scheduled=disturbance_family is not None,
                        operator_applied=self.cfg.operator_disturbance)  # family deliberately omitted
            ctrl = self._make_controller(deployed)
            try:
                prof = self.cfg.profile
                det = DegradationDetector(self.plant.dt, window_s=prof.monitor_window_s, factor=prof.monitor_factor,
                                          floor=prof.monitor_floor, hold_s=prof.monitor_hold_s)
                mk: dict[str, Any] = {}
                if self.cfg.operator_disturbance:
                    mk["pause_for_operator"] = self._operator_pause
                    mk["disturbance_at_s"] = self.cfg.monitor_pre_s
                res = run_monitored_rollout(
                    self.plant, ctrl, self.sup, duration_s=self.cfg.monitor_duration_s, target=self.s.objective.target,
                    seed=self.cfg.plant_seed, disturbance=spec, calibrate_s=self.cfg.monitor_calibrate_s,
                    detector=det, stop_after_detection_s=self.cfg.monitor_post_detection_s, profile=prof, **mk,
                )
            finally:
                ctrl.close()
                self._idle_physical_plant("after monitored rollout")
            m.pre_trace, m.post_trace = res.pre_trace, res.post_trace
            op_t = res.trace.meta.get("operator_disturbance_at_s") if res.trace.meta else None
            if op_t is not None:
                self._event("operator_disturbance_applied", t=op_t)
            if res.trace.steps:
                self._last_u = float(res.trace.steps[-1].u_applied)
                self._last_u_change_t = float(res.trace.steps[-1].t)
            m.degraded = res.degraded_at_t is not None
            m.degraded_at_t = res.degraded_at_t
            m.baseline_window_mae = res.detector_state.get("baseline_window_mae")
            m.recent_window_mae = res.detector_state.get("recent_window_mae")
            self.store.write_json("monitoring.json", {"detector": res.detector_state, "degraded_at_t": res.degraded_at_t,
                                                      "trace": res.trace.model_dump(mode="json")})
            self._event("monitoring_result", degraded=m.degraded, degraded_at_t=m.degraded_at_t, detector=res.detector_state)
            if not m.degraded:
                self._transition("COMPLETE", reason="no degradation detected; deployed controller retained")
                return self.s
            self._transition("ADAPTING", attempt=0, parent=deployed.candidate_id, reidentifying=True)
            self._reidentify()
            self._idle_physical_plant("after re-identification")
            if self._twin_mode():
                # Physical-plant path: refit the twin on the after-change experiments so v1 and v2 are
                # scored on a model of the machine AS IT NOW IS, not on a generic version of the family.
                self._fit_changed_twin(disturbance_family)
                deployed.disturbance_evaluation = self._evaluate_changed(deployed, disturbance_family)
            elif disturbance_family:
                # Simulator path: score frozen v1 on the family's disturbance suite (same scenarios v2 will face).
                deployed.disturbance_evaluation = self._evaluate_disturbance(deployed, disturbance_family)
            self._adapt(deployed, disturbance_family)
        except _Stop as e:
            self._transition("STOPPED", reason=str(e))
        except MuseError as e:
            self._event("error", error=f"model: {e}")
            self._transition("FAILED", reason=f"model error during adaptation: {e}")
        except Exception as e:
            log.exception("unexpected error during monitoring/adaptation")
            self._event("error", error=f"unexpected: {type(e).__name__}: {e}")
            self._transition("FAILED", reason=f"unexpected error: {type(e).__name__}: {e}")
        finally:
            self._idle_physical_plant("end of run")
            self._persist_summary()
        return self.s

    def _twin_mode(self) -> bool:
        return self.cfg.eval_plant_factory == "twin"

    def _fit_changed_twin(self, family: str | None) -> None:
        """Trusted: fit a second twin from the after-change experiments (the machine as it now is)."""
        from backend.plant.thermal_twin import fit_twin, twin_factory

        traces = [e.trace for e in self.s.experiments if e.trace is not None and e.status == "completed"
                  and e.phase == "after_change"]
        self._changed_factory = None
        if len(traces) < 2:
            self._event("changed_twin_skipped", reason=f"only {len(traces)} after-change experiments; falling back to the "
                        f"family disturbance on the original twin")
            return
        try:
            params = fit_twin(traces, dt=self.plant.dt)
        except ValueError as e:
            self._event("changed_twin_skipped", reason=f"fit failed: {e}")
            return
        report = getattr(params, "report", None)
        self._changed_factory = twin_factory(params)
        self.store.write_json("twin_fit_after_change.json", params.model_dump(mode="json"))
        self._event("changed_twin_fitted", n_traces=len(traces), declared_family_known_to_operator_only=family is not None,
                    report=report.model_dump(mode="json") if hasattr(report, "model_dump") else report)

    def _evaluate_changed(self, cand: CandidateRecord, family: str | None) -> EvaluationReport:
        """Score a candidate on the changed-machine twin (no scheduled disturbance: the twin IS the changed
        machine). Falls back to the generic family suite on the original twin if no changed twin exists."""
        if getattr(self, "_changed_factory", None) is None:
            if family:
                return self._evaluate_disturbance(cand, family)
            raise MuseError("no changed twin and no declared family; cannot score the repair")
        report = evalsuite.evaluate_heldout(lambda: self._make_controller(cand), candidate_id=cand.candidate_id,
                                            plant_seed=self.cfg.plant_seed, limits=self.sup.limits,
                                            profile=self.cfg.profile, plant_factory=self._changed_factory)
        report.suite = "disturbance:changed_machine"
        report.gate_name = "G3-candidate"
        report.comparison["post_disturbance_mae"] = {str(e.index): e.metrics.mae for e in report.episodes}
        report.aggregate["median_post_disturbance_mae"] = float(sorted(e.metrics.mae for e in report.episodes)[len(report.episodes) // 2])
        safe = all(e.metrics.hard_violations == 0 and e.metrics.invalid_outputs == 0 for e in report.episodes)
        report.gate_passed = safe
        n_safe = sum(1 for e in report.episodes if e.metrics.hard_violations == 0 and e.metrics.invalid_outputs == 0)
        report.gate_reasons = [f"{n_safe}/{len(report.episodes)} episodes safe on the changed-machine twin",
                               "G3-candidate " + ("passed" if safe else "failed")]
        self.store.write_json(f"evaluation_disturbance_v{cand.version}.json", report.model_dump(mode="json"))
        self._event("evaluation", candidate_id=cand.candidate_id, suite="disturbance", gate=report.gate_name,
                    gate_passed=report.gate_passed, reasons=report.gate_reasons, aggregate=report.aggregate,
                    scored_on="changed_machine_twin")
        return report

    def _evaluate_disturbance(self, cand: CandidateRecord, family: str) -> EvaluationReport:
        kw: dict[str, Any] = {"profile": self.cfg.profile}
        if self._eval_factory() is not None:
            kw["plant_factory"] = self._eval_factory()
        report = evalsuite.evaluate_disturbance(lambda: self._make_controller(cand), family, candidate_id=cand.candidate_id,
                                                plant_seed=self.cfg.plant_seed, limits=self.sup.limits, **kw)
        self.store.write_json(f"evaluation_disturbance_v{cand.version}.json", report.model_dump(mode="json"))
        self._event("evaluation", candidate_id=cand.candidate_id, suite="disturbance", gate=report.gate_name,
                    gate_passed=report.gate_passed, reasons=report.gate_reasons, aggregate=report.aggregate)
        return report

    def _adapt(self, deployed: CandidateRecord, family: str | None) -> None:
        parent = deployed
        for attempt in range(1, self.cfg.max_adaptation_attempts + 1):
            if self.s.candidates_remaining() <= 0:
                self._transition("FAILED", reason="candidate budget exhausted during adaptation; v1 retained")
                return
            self._check_budget()
            self._transition("ADAPTING", attempt=attempt, parent=parent.candidate_id)
            view = build_agent_view(self.s)
            feedback = self._adaptation_feedback(parent)
            sub = self._ask("adapting", revision_messages(view, self._source(parent), feedback), RevisionSubmission, view)
            cand = self._register(sub, parent, "revision")
            cand = self._validate_contract(cand, view)
            if cand.status.startswith("rejected"):
                parent = cand
                continue
            self._transition("EVALUATING", candidate_id=cand.candidate_id)
            nominal = self._evaluate_heldout(cand)
            if not family:
                cand.status = "approved" if nominal.gate_passed else "failed_gate"
                self._transition("COMPLETE" if nominal.gate_passed else "FAILED", candidate_id=cand.candidate_id)
                return
            dist = self._evaluate_changed(cand, family) if self._twin_mode() else self._evaluate_disturbance(cand, family)
            cand.disturbance_evaluation = dist
            cmp = evalsuite.compare_adaptation(deployed.disturbance_evaluation, dist) if deployed.disturbance_evaluation else {}
            diag_ok = _diagnosis_matches(getattr(sub, "diagnosis_category", "unknown"), family)
            self.store.write_json(f"adaptation_v{cand.version}.json", {"comparison": cmp, "nominal_gate": nominal.gate_passed,
                                                                      "diagnosis_category": sub.diagnosis_category,
                                                                      "diagnosis_correct": diag_ok})
            self._event("adaptation_result", candidate_id=cand.candidate_id, gate3_passed=cmp.get("gate_passed"),
                        n_improved=cmp.get("n_improved"), median_reduction=cmp.get("median_reduction"),
                        nominal_gate_passed=nominal.gate_passed, diagnosis_correct=diag_ok)
            # Promotion rule (decided 2026-10-31): the repaired controller is judged on the machine as it
            # now is: >= GATE3_MIN_PASS scenarios improved by >= GATE3_MIN_MAE_REDUCTION and zero hard
            # violations / invalid outputs on the post-change suite. Nominal (pre-change) performance is
            # re-scored and reported next to it, not gated.
            if cmp.get("gate_passed"):
                cand.status = "approved"
                self._transition("COMPLETE", candidate_id=cand.candidate_id,
                                 reason=f"v{cand.version} promoted (nominal G2 after repair: {'pass' if nominal.gate_passed else 'fail'})")
                return
            cand.status = "failed_gate"
            parent = cand
        self._transition("FAILED", reason="adaptation attempts exhausted; last approved controller retained")

    def _reidentify(self) -> None:
        """Protocol v1.1: bounded experiments on the CHANGED machine (disturbance active) before revising.

        The live plant continues from the end of the monitored rollout, so the disturbance is in
        effect. The agent sees only measured traces, as always."""
        while self.s.reidentification_remaining() > 0:
            self._check_budget()
            self.s.current_obs = self.plant.observe()
            view = build_agent_view(self.s)
            proposal: ExperimentProposal = self._ask("reidentifying", reidentify_messages(view), ExperimentProposal, view)
            self.s.record_ledger(proposal.hypotheses, after_experiment=self.s.experiments[-1].id if self.s.experiments else None)
            self._event("ledger", hypotheses=[h.model_dump() for h in proposal.hypotheses],
                        operator_note=proposal.operator_note, phase="after_change")
            if proposal.ready_to_generate:
                self._event("ready_to_revise", justification=proposal.readiness_justification)
                return
            self._run_experiment(proposal, phase="after_change")
        self._event("reidentification_budget_exhausted")

    def _idle_physical_plant(self, when: str) -> None:
        """Real hardware only: between stages (authoring, gating, model calls) nothing steps the plant, so
        the last command would be held open-loop for minutes. Turn the actuator off and record it. The
        simulator path is untouched: its state does not evolve between stages."""
        if not getattr(self.plant, "is_physical", False):
            return
        with contextlib.suppress(Exception):
            self.plant.emergency_stop()
        self._last_u = 0.0
        self._event("actuator_idled", when=when)

    def _operator_pause(self) -> Callable[[], bool]:
        """Physical plants: ask the operator to apply the disturbance. Non-blocking: the control loop keeps
        running (the heater stays under control) while a thread waits for Enter; the monitor records the
        first tick after Enter as the disturbance time. Logged, never described to the agent."""
        trigger = self.store.dir / "OPERATOR_GO"
        interactive = sys.stdin is not None and sys.stdin.isatty()
        self._event("operator_disturbance_prompt", note="operator asked to apply the physical change now",
                    mechanism="stdin" if interactive else "trigger_file", trigger=None if interactive else str(trigger))
        done = threading.Event()

        def _wait() -> None:
            if interactive:
                try:
                    input("\n>>> Apply the physical disturbance now, then press Enter (control keeps running)... ")
                except EOFError:
                    pass
            else:
                # No keyboard (launched from a tool or a service): an EOF on stdin must not count as "applied".
                # Wait for the operator to create the trigger file instead.
                print(f"\n>>> Apply the physical disturbance now, then create {trigger} (control keeps running)... ",
                      flush=True)
                while not trigger.exists():
                    time.sleep(0.5)
            done.set()

        threading.Thread(target=_wait, name="operator-prompt", daemon=True).start()
        return done.is_set

    def _adaptation_feedback(self, parent: CandidateRecord) -> str:
        m = self.s.monitoring
        n_after = len([e for e in self.s.experiments if e.phase == "after_change" and e.status == "completed"])
        lines = ["The deployed controller's tracking degraded during a monitored run.",
                 f"Rolling-window MAE before: {m.baseline_window_mae}; after: {m.recent_window_mae}.",
                 "Traces before and after the change are in the session view under monitoring.",
                 f"You ran {n_after} experiments on the changed machine (phase 'after_change'); use them to quantify the change."]
        if parent.disturbance_evaluation is not None:
            rep = parent.disturbance_evaluation.agent_safe(include_traces=False)
            lines.append(f"Re-scored on post-change scenarios: {rep['aggregate']} (episodes in view under candidates[].post_change_evaluation).")
        if parent.status.startswith("rejected"):
            lines.append(self._feedback_for(parent))
        elif parent.status == "failed_gate" and parent.disturbance_evaluation is not None:
            lines.append("Your previous revision did not improve enough on the post-change scenarios, or broke nominal behaviour.")
        return self._scrub("\n".join(lines))

    # ================================================================ summary
    def _profile_summary(self) -> dict[str, Any]:
        p = self.cfg.profile
        return {"name": p.name, "dt": p.dt, "target": p.target, "band": list(p.band), "y_unit": p.y_unit,
                "y_scale": p.y_scale, "y_offset": p.y_offset, "episode_s": p.episode_s, "settle_s": p.settle_s,
                "eval_plant": "twin" if self.cfg.eval_plant_factory == "twin" else ("custom" if callable(self.cfg.eval_plant_factory) else "simulator"),
                "operator_disturbance": self.cfg.operator_disturbance}

    def _persist_summary(self) -> None:
        agent_totals = getattr(self.agent, "totals", None)
        summary = {
            "run_id": self.s.run_id, "stage": self.s.stage, "model_id": self.s.model_id, "agent_mode": self.s.agent_mode,
            "prompt_version": PROMPT_VERSION, "prompt_hash": PROMPT_HASH, "sandbox_mode": self.cfg.sandbox_mode,
            "profile": self._profile_summary(),
            "experiments": [e.model_dump(exclude={"trace"}) for e in self.s.experiments],
            "ledger_history": self.s.ledger_history,
            "candidates": [c.model_dump(exclude={"evaluation", "disturbance_evaluation"}) for c in self.s.candidates],
            "monitoring": self.s.monitoring.model_dump(exclude={"pre_trace", "post_trace"}),
            "stage_history": self.s.stage_history,
            "model_usage": agent_totals.__dict__ if agent_totals else None,
            "elapsed_s": round(self.s.elapsed_s(), 1),
            "finished_at": time.time(),
        }
        self.store.write_json("result.json", summary)
        self.store.write_json("hypothesis_ledger.json", self.s.ledger_history)


class _Stop(Exception):
    pass


def _diagnosis_matches(category: str, family: str | None) -> bool | None:
    """Trusted, after-the-fact scoring of Muse's diagnosis. The mapping is the benchmark's."""
    if family is None:
        return None
    expected = {"pump_derate": "actuator_weaker", "extra_leak": "outflow_increased",
                "drain_shift": "outflow_increased", "actuator_lag": "response_slower"}
    return expected.get(family) == category


def is_finite_number(x: Any) -> bool:
    try:
        return math.isfinite(float(x))
    except (TypeError, ValueError):
        return False
