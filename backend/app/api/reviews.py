"""QA review queue, overrides, scoring-run retrieval and audit endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.api.mappers import scoring_run_out
from app.db.session import get_db
from app.repositories import scoring as scoring_repo
from app.schemas.audit import AuditEventOut
from app.schemas.demo import RunDiff
from app.schemas.review import HumanReviewOut, OpenReviewRequest, QueueItemOut
from app.schemas.scoring import CheckResultOut, OverrideRequest, ScoringRunOut
from app.services.scoring.compare import RunComparisonError, compare_runs
from app.services.review import (
    CheckResultNotFoundError,
    InvalidOverrideError,
    build_review_queue,
    open_review,
    override_check_result,
)

router = APIRouter(tags=["review"])


@router.get("/reviews", response_model=list[QueueItemOut])
def review_queue(
    queue: str = Query(default="NEEDS_REVIEW", description="NEEDS_REVIEW | HOLD | APPROVED | ALL"),
    db: Session = Depends(get_db),
) -> list[QueueItemOut]:
    return [QueueItemOut(**item.__dict__) for item in build_review_queue(db, queue)]


@router.post("/reviews/{lead_id}/open", response_model=HumanReviewOut)
def open_lead_review(
    lead_id: int, payload: OpenReviewRequest, db: Session = Depends(get_db)
) -> HumanReviewOut:
    review = open_review(db, lead_id, payload.actor)
    if review is None:
        raise HTTPException(status_code=404, detail=f"Lead {lead_id} has no scoring run to review.")
    return HumanReviewOut.model_validate(review)


@router.post("/check-results/{check_result_id}/override", response_model=ScoringRunOut)
def override(
    check_result_id: int, payload: OverrideRequest, db: Session = Depends(get_db)
) -> ScoringRunOut:
    try:
        _, run = override_check_result(
            db,
            check_result_id=check_result_id,
            override_status=payload.override_status,
            reason_code=payload.reason_code,
            notes=payload.notes,
            actor=payload.actor,
        )
    except CheckResultNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except InvalidOverrideError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return scoring_run_out(scoring_repo.get_run(db, run.id))


@router.get("/check-results/{check_result_id}", response_model=CheckResultOut)
def get_check_result(check_result_id: int, db: Session = Depends(get_db)) -> CheckResultOut:
    result = scoring_repo.get_check_result(db, check_result_id)
    if result is None:
        raise HTTPException(status_code=404, detail=f"Check result {check_result_id} was not found.")
    return CheckResultOut.model_validate(result)


@router.get("/scoring-runs/{run_id}", response_model=ScoringRunOut)
def get_scoring_run(run_id: int, db: Session = Depends(get_db)) -> ScoringRunOut:
    run = scoring_repo.get_run(db, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail=f"Scoring run {run_id} was not found.")
    return scoring_run_out(run)


@router.get("/audit-events", response_model=list[AuditEventOut])
def audit_events(
    lead_id: int | None = None,
    event_type: str | None = None,
    limit: int = Query(default=100, le=500),
    db: Session = Depends(get_db),
) -> list[AuditEventOut]:
    events = scoring_repo.list_audit_events(db, lead_id=lead_id, event_type=event_type, limit=limit)
    return [AuditEventOut.model_validate(event) for event in events]

@router.get("/scoring-runs/{run_id}/diff/{other_run_id}", response_model=RunDiff)
def diff_runs(run_id: int, other_run_id: int, db: Session = Depends(get_db)) -> dict:
    """What changed between two runs of the same sale (run_id is the newer one)."""
    target = scoring_repo.get_run(db, run_id)
    base = scoring_repo.get_run(db, other_run_id)
    if target is None or base is None:
        raise HTTPException(status_code=404, detail="One of those scoring runs was not found.")
    try:
        return compare_runs(base, target)
    except RunComparisonError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
