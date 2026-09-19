"""Human review: the override path and the review queue.

An override is strictly additive. The machine's CheckResult.status is never
written to; a HumanOverride row is appended carrying the original status,
the new status, a reason code, free-text notes, the actor and the time. The
run's gate is then recomputed into ``override_gate_result``, leaving the
original machine ``gate_result`` intact for audit.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.enums import (
    AuditEventType,
    CheckStatus,
    ExecutionStatus,
    GateDecision,
    OverrideReasonCode,
    ReviewStatus,
)
from app.models import CheckResult, HumanOverride, HumanReview, Lead, ScoringRun
from app.repositories import scoring as scoring_repo
from app.services.audit import record_event
from app.services.scoring.engine import recompute_gate_with_overrides


class CheckResultNotFoundError(LookupError):
    pass


class InvalidOverrideError(ValueError):
    pass


@dataclass
class QueueItem:
    lead_id: int
    scoring_run_id: int
    retailer_name: str
    vertical_code: str
    agent_name: str | None
    call_datetime: datetime
    gate_result: str
    machine_gate_result: str
    reason: str
    critical_fail_count: int
    critical_uncertain_count: int
    incomplete_count: int
    priority: int
    qa_score_weighted: float | None


def override_check_result(
    db: Session,
    *,
    check_result_id: int,
    override_status: CheckStatus,
    reason_code: OverrideReasonCode,
    notes: str,
    actor: str,
) -> tuple[CheckResult, ScoringRun]:
    if not notes or not notes.strip():
        raise InvalidOverrideError("Override notes are mandatory.")

    result = scoring_repo.get_check_result(db, check_result_id)
    if result is None:
        raise CheckResultNotFoundError(f"Check result {check_result_id} was not found.")

    run = scoring_repo.get_run(db, result.scoring_run_id)
    if run is None:  # pragma: no cover - referential integrity makes this unreachable
        raise CheckResultNotFoundError(f"Scoring run for check result {check_result_id} is missing.")

    override = HumanOverride(
        check_result_id=result.id,
        original_status=result.status,
        override_status=override_status.value,
        reason_code=reason_code.value,
        notes=notes.strip(),
        actor=actor,
    )
    db.add(override)
    db.flush()
    db.refresh(result)

    gate = recompute_gate_with_overrides(run)
    run.override_gate_result = gate.decision.value
    summary = dict(run.summary or {})
    summary["override_gate_reason"] = gate.reason
    summary["override_triggering_checks"] = gate.triggering_checks
    run.summary = summary

    _ensure_open_review(db, run, actor)

    record_event(
        db,
        event_type=AuditEventType.CHECK_OVERRIDDEN,
        entity_type="check_result",
        entity_id=result.id,
        actor=actor,
        lead_id=run.lead_id,
        details={
            "check_code": result.check_code,
            "check_name": result.check_name,
            "original_status": result.status,
            "override_status": override_status.value,
            "reason_code": reason_code.value,
            "notes": notes.strip(),
            "machine_gate_result": run.gate_result,
            "gate_after_override": gate.decision.value,
        },
    )

    db.commit()
    db.refresh(run)
    db.refresh(result)
    return result, run


def _ensure_open_review(db: Session, run: ScoringRun, actor: str) -> HumanReview:
    existing = db.scalars(
        select(HumanReview)
        .where(HumanReview.scoring_run_id == run.id)
        .where(HumanReview.status == ReviewStatus.OPEN.value)
    ).first()
    if existing is not None:
        return existing

    review = HumanReview(
        lead_id=run.lead_id,
        scoring_run_id=run.id,
        opened_by=actor,
        status=ReviewStatus.OPEN.value,
    )
    db.add(review)
    db.flush()
    record_event(
        db,
        event_type=AuditEventType.HUMAN_REVIEW_OPENED,
        entity_type="human_review",
        entity_id=review.id,
        actor=actor,
        lead_id=run.lead_id,
        details={"scoring_run_id": run.id},
    )
    return review


def open_review(db: Session, lead_id: int, actor: str) -> HumanReview | None:
    run = scoring_repo.latest_run(db, lead_id)
    if run is None:
        return None
    review = _ensure_open_review(db, run, actor)
    db.commit()
    db.refresh(review)
    return review


def close_review(db: Session, review_id: int, actor: str, notes: str = "") -> HumanReview | None:
    review = db.get(HumanReview, review_id)
    if review is None:
        return None
    review.status = ReviewStatus.CLOSED.value
    review.closed_at = datetime.now(UTC)
    if notes:
        review.notes = notes
    db.commit()
    db.refresh(review)
    return review


_QUEUE_FILTERS = {
    "NEEDS_REVIEW": {GateDecision.HUMAN_REVIEW.value},
    "HOLD": {GateDecision.HOLD.value},
    "APPROVED": {GateDecision.APPROVED.value},
    "ALL": {d.value for d in GateDecision},
}


def build_review_queue(db: Session, queue_filter: str = "NEEDS_REVIEW") -> list[QueueItem]:
    """Leads whose latest run needs attention, most urgent first.

    Priority: critical UNCERTAIN (a human must decide) outranks critical FAIL
    (already decided, just blocked), which outranks incomplete execution.
    """
    wanted = _QUEUE_FILTERS.get(queue_filter.upper(), _QUEUE_FILTERS["NEEDS_REVIEW"])

    leads = {lead.id: lead for lead in db.scalars(select(Lead))}
    latest = scoring_repo.latest_runs_for_leads(db, list(leads))

    items: list[QueueItem] = []
    for lead_id, run in latest.items():
        gate = run.effective_gate_result
        if gate not in wanted:
            continue

        lead = leads[lead_id]
        critical_fail = sum(
            1
            for r in run.check_results
            if r.critical and r.effective_status == CheckStatus.FAIL.value
        )
        critical_uncertain = sum(
            1
            for r in run.check_results
            if r.critical and r.effective_status == CheckStatus.UNCERTAIN.value
        )
        incomplete = sum(
            1
            for r in run.check_results
            if r.execution_status != ExecutionStatus.COMPLETED.value
            and r.status != CheckStatus.NOT_APPLICABLE.value
        )

        if critical_uncertain:
            priority = 1
        elif critical_fail:
            priority = 2
        elif incomplete:
            priority = 3
        else:
            priority = 4

        items.append(
            QueueItem(
                lead_id=lead_id,
                scoring_run_id=run.id,
                retailer_name=lead.retailer.name,
                vertical_code=lead.vertical.code,
                agent_name=lead.agent.name if lead.agent else None,
                call_datetime=lead.call_datetime,
                gate_result=gate,
                machine_gate_result=run.gate_result,
                reason=(run.summary or {}).get("override_gate_reason") or run.gate_reason,
                critical_fail_count=critical_fail,
                critical_uncertain_count=critical_uncertain,
                incomplete_count=incomplete,
                priority=priority,
                qa_score_weighted=run.qa_score_weighted,
            )
        )

    items.sort(key=lambda item: (item.priority, -item.lead_id))
    return items
