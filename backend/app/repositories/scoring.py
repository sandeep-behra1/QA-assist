"""Scoring run, check result and audit data access."""

from __future__ import annotations

from sqlalchemy import desc, select
from sqlalchemy.orm import Session, selectinload

from app.models import AuditEvent, CheckResult, HumanOverride, ScoringRun


def _run_loader_options():
    return (
        selectinload(ScoringRun.check_results).selectinload(CheckResult.evidence),
        selectinload(ScoringRun.check_results).selectinload(CheckResult.overrides),
    )


def get_run(db: Session, run_id: int) -> ScoringRun | None:
    stmt = select(ScoringRun).where(ScoringRun.id == run_id).options(*_run_loader_options())
    return db.scalars(stmt).first()


def runs_for_lead(db: Session, lead_id: int) -> list[ScoringRun]:
    stmt = (
        select(ScoringRun)
        .where(ScoringRun.lead_id == lead_id)
        .order_by(desc(ScoringRun.id))
        .options(*_run_loader_options())
    )
    return list(db.scalars(stmt))


def latest_run(db: Session, lead_id: int) -> ScoringRun | None:
    stmt = (
        select(ScoringRun)
        .where(ScoringRun.lead_id == lead_id)
        .order_by(desc(ScoringRun.id))
        .options(*_run_loader_options())
    )
    return db.scalars(stmt).first()


def latest_runs_for_leads(db: Session, lead_ids: list[int]) -> dict[int, ScoringRun]:
    """Most recent run per lead, for list/dashboard views."""
    if not lead_ids:
        return {}
    stmt = (
        select(ScoringRun)
        .where(ScoringRun.lead_id.in_(lead_ids))
        .order_by(ScoringRun.lead_id, desc(ScoringRun.id))
        .options(selectinload(ScoringRun.check_results).selectinload(CheckResult.overrides))
    )
    latest: dict[int, ScoringRun] = {}
    for run in db.scalars(stmt):
        latest.setdefault(run.lead_id, run)
    return latest


def get_check_result(db: Session, check_result_id: int) -> CheckResult | None:
    stmt = (
        select(CheckResult)
        .where(CheckResult.id == check_result_id)
        .options(selectinload(CheckResult.evidence), selectinload(CheckResult.overrides))
    )
    return db.scalars(stmt).first()


def list_overrides(db: Session, lead_id: int | None = None) -> list[HumanOverride]:
    stmt = select(HumanOverride).order_by(desc(HumanOverride.id))
    if lead_id is not None:
        stmt = stmt.join(CheckResult).join(ScoringRun).where(ScoringRun.lead_id == lead_id)
    return list(db.scalars(stmt))


def list_audit_events(
    db: Session,
    lead_id: int | None = None,
    event_type: str | None = None,
    limit: int = 200,
) -> list[AuditEvent]:
    stmt = select(AuditEvent).order_by(desc(AuditEvent.id)).limit(limit)
    if lead_id is not None:
        stmt = stmt.where(AuditEvent.lead_id == lead_id)
    if event_type:
        stmt = stmt.where(AuditEvent.event_type == event_type)
    return list(db.scalars(stmt))
