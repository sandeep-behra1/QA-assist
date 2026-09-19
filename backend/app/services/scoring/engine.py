"""Scoring orchestration.

Flow, per scoring run:

    resolve checklist version for the call date  (never "latest")
    -> build authoritative context from trusted rows
    -> for each active check: applicability -> evaluator -> CheckResult
    -> deterministic gate over the results
    -> QA score (reported, not gating)
    -> audit events

Runs are append-only: re-scoring inserts a new ScoringRun and leaves every
earlier run byte-for-byte intact.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.enums import (
    AuditEventType,
    CheckStatus,
    ConfidenceLevel,
    ExecutionStatus,
    GateDecision,
    LeadStatus,
    ScoringRunStatus,
)
from app.models import CheckDefinition, CheckResult, Evidence, Lead, ScoringRun, Transcript
from app.repositories import catalog as catalog_repo
from app.repositories import checklists as checklist_repo
from app.repositories import leads as leads_repo
from app.services.audit import json_safe, record_event
from app.services.gate.policy import GateInput, GateOutcome, apply_gate_policy
from app.services.llm import EvidenceInterpreter, get_evidence_interpreter
from app.services.rules.applicability import is_applicable
from app.services.rules.resolver import NoApplicableChecklistError, resolve_checklist_version
from app.services.rules.sources import build_authoritative_context
from app.services.scoring.context import EvaluationContext, EvaluationOutcome
from app.services.scoring.qa_score import ScoreInput, calculate_qa_score
from app.services.scoring.registry import get_evaluator


class LeadNotFoundError(LookupError):
    pass


class TranscriptRequiredError(RuntimeError):
    """A sale cannot be scored without a transcript -- refusing is safer than
    producing an empty run that might read as 'nothing wrong found'."""


def score_lead(
    db: Session,
    lead_id: int,
    actor: str = "system",
    interpreter: EvidenceInterpreter | None = None,
    settings: Settings | None = None,
) -> ScoringRun:
    settings = settings or get_settings()
    interpreter = interpreter or get_evidence_interpreter(settings)

    lead = leads_repo.get_lead(db, lead_id)
    if lead is None:
        raise LeadNotFoundError(f"Lead {lead_id} was not found.")

    transcript = leads_repo.latest_transcript(db, lead_id)
    if transcript is None or not transcript.segments:
        raise TranscriptRequiredError(
            f"Lead {lead_id} has no transcript, so it cannot be scored yet."
        )

    call_date = lead.call_datetime.date()
    versions = checklist_repo.versions_for_retailer_vertical(db, lead.retailer_id, lead.vertical_id)
    version = resolve_checklist_version(versions, call_date)
    if version is None:
        raise NoApplicableChecklistError(lead.retailer_id, lead.vertical_id, call_date)

    plan = lead.plan
    rate_card = (
        catalog_repo.get_rate_card_for_date(db, plan.id, call_date) if plan is not None else None
    )
    call = transcript.call or (lead.calls[0] if lead.calls else None)
    context = build_authoritative_context(lead, lead.retailer, plan, rate_card, call)

    run = ScoringRun(
        lead_id=lead.id,
        checklist_version_id=version.id,
        transcript_id=transcript.id,
        status=ScoringRunStatus.RUNNING.value,
        evaluator_metadata={
            "interpreter_provider": settings.llm_provider,
            "interpreter_model": settings.llm_model,
            "asr_confidence_floor": settings.asr_confidence_floor,
            "rate_card_id": rate_card.id if rate_card else None,
            "checklist_version": version.version_number,
        },
    )
    db.add(run)
    db.flush()

    record_event(
        db,
        event_type=AuditEventType.SCORING_STARTED,
        entity_type="scoring_run",
        entity_id=run.id,
        actor=actor,
        lead_id=lead.id,
        details={"checklist_version_id": version.id, "transcript_id": transcript.id},
    )

    results = [
        _evaluate_check(db, run, check, transcript, context, interpreter, settings, lead)
        for check in sorted(version.checks, key=lambda c: (c.display_order, c.id))
    ]

    gate = apply_gate_policy(
        [
            GateInput(
                check_code=result.check_code,
                critical=result.critical,
                status=result.status,
                execution_status=result.execution_status,
                blocking_behavior=result.blocking_behavior,
            )
            for result in results
        ]
    )
    score = calculate_qa_score(
        [ScoreInput(critical=r.critical, status=r.status, weight=r.weight) for r in results]
    )

    run.status = ScoringRunStatus.COMPLETED.value
    run.completed_at = datetime.now(UTC)
    run.gate_result = gate.decision.value
    run.gate_reason = gate.reason
    run.qa_score_raw = score.raw_percent
    run.qa_score_weighted = score.weighted_percent
    run.summary = json_safe({**score.as_dict(), "triggering_checks": gate.triggering_checks})

    lead.status = LeadStatus.SCORED.value

    record_event(
        db,
        event_type=AuditEventType.SCORING_COMPLETED,
        entity_type="scoring_run",
        entity_id=run.id,
        actor=actor,
        lead_id=lead.id,
        details={
            "gate_result": gate.decision.value,
            "gate_reason": gate.reason,
            "qa_score_weighted": score.weighted_percent,
            "summary": score.as_dict(),
        },
    )
    _record_gate_outcome_event(db, run, gate, actor)

    db.commit()
    db.refresh(run)
    return run


def _record_gate_outcome_event(
    db: Session, run: ScoringRun, gate: GateOutcome, actor: str
) -> None:
    event_type = {
        GateDecision.APPROVED: AuditEventType.SALE_APPROVED,
        GateDecision.HOLD: AuditEventType.SALE_HOLD,
        GateDecision.HUMAN_REVIEW: AuditEventType.SALE_ROUTED_TO_REVIEW,
    }[gate.decision]
    record_event(
        db,
        event_type=event_type,
        entity_type="scoring_run",
        entity_id=run.id,
        actor=actor,
        lead_id=run.lead_id,
        details={"reason": gate.reason, "triggering_checks": gate.triggering_checks},
    )


def _evaluate_check(
    db: Session,
    run: ScoringRun,
    check: CheckDefinition,
    transcript: Transcript,
    context: dict,
    interpreter: EvidenceInterpreter,
    settings: Settings,
    lead: Lead,
) -> CheckResult:
    rule_version = f"{check.checklist_version.checklist.code}:v{check.checklist_version.version_number}"

    if not check.active:
        outcome = EvaluationOutcome(
            status=CheckStatus.NOT_APPLICABLE,
            reason="Check is inactive in this checklist version.",
            confidence_level=ConfidenceLevel.HIGH,
        )
        return _persist_result(db, run, check, outcome, transcript, rule_version)

    applicable, applicability_reason = is_applicable(check.applicable_conditions, context)
    if not applicable:
        outcome = EvaluationOutcome(
            status=CheckStatus.NOT_APPLICABLE,
            reason=f"Check does not apply to this sale: {applicability_reason}",
            confidence_level=ConfidenceLevel.HIGH,
        )
        return _persist_result(db, run, check, outcome, transcript, rule_version)

    evaluator = get_evaluator(check.evaluation_method)
    if evaluator is None:
        outcome = EvaluationOutcome(
            status=CheckStatus.UNCERTAIN,
            execution_status=ExecutionStatus.ERROR,
            confidence_level=ConfidenceLevel.LOW,
            reason=f"No evaluator is registered for method '{check.evaluation_method}'.",
        )
        return _persist_result(db, run, check, outcome, transcript, rule_version)

    ctx = EvaluationContext(
        check=check,
        segments=list(transcript.segments),
        authoritative_context=context,
        interpreter=interpreter,
        settings=settings,
        reference_date=lead.call_datetime.date(),
    )

    try:
        outcome = evaluator(ctx)
    except Exception as exc:  # noqa: BLE001 - an evaluator crash must escalate, never approve
        outcome = EvaluationOutcome(
            status=CheckStatus.UNCERTAIN,
            execution_status=ExecutionStatus.ERROR,
            confidence_level=ConfidenceLevel.LOW,
            reason=f"Evaluator raised an unexpected error: {exc}",
        )

    return _persist_result(db, run, check, outcome, transcript, rule_version)


def _persist_result(
    db: Session,
    run: ScoringRun,
    check: CheckDefinition,
    outcome: EvaluationOutcome,
    transcript: Transcript,
    rule_version: str,
) -> CheckResult:
    result = CheckResult(
        scoring_run_id=run.id,
        check_definition_id=check.id,
        check_code=check.code,
        check_name=check.name,
        check_type=check.check_type,
        evaluation_method=check.evaluation_method,
        critical=check.critical,
        blocking_behavior=check.blocking_behavior,
        weight=check.weight,
        display_order=check.display_order,
        rule_version=rule_version,
        status=outcome.status.value,
        execution_status=outcome.execution_status.value,
        confidence_level=outcome.confidence_level.value if outcome.confidence_level else None,
        reason=outcome.reason,
        observed_value=outcome.observed_value,
        expected_value=outcome.expected_value,
        llm_metadata=json_safe(outcome.llm_metadata or {}),
    )
    db.add(result)
    db.flush()

    for ref in outcome.evidence:
        db.add(
            Evidence(
                check_result_id=result.id,
                transcript_id=transcript.id,
                segment_id=ref.segment.segment_id,
                speaker=ref.segment.speaker,
                text=ref.segment.text,
                start_time=ref.segment.start_time,
                end_time=ref.segment.end_time,
                asr_confidence=ref.segment.asr_confidence,
                extraction_method=ref.extraction_method,
            )
        )
    db.flush()
    return result


def recompute_gate_with_overrides(run: ScoringRun) -> GateOutcome:
    """Recalculate the gate using human-corrected statuses.

    The machine's ``gate_result`` and each CheckResult.status stay untouched;
    only ``override_gate_result`` reflects this outcome.
    """
    return apply_gate_policy(
        [
            GateInput(
                check_code=result.check_code,
                critical=result.critical,
                status=result.effective_status,
                execution_status=result.execution_status,
                blocking_behavior=result.blocking_behavior,
            )
            for result in run.check_results
        ]
    )
