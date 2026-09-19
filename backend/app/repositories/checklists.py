"""Checklist data access."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models import CheckDefinition, Checklist, ChecklistVersion


def list_checklists(
    db: Session, retailer_id: int | None = None, vertical_id: int | None = None
) -> list[Checklist]:
    stmt = (
        select(Checklist)
        .order_by(Checklist.name)
        .options(selectinload(Checklist.versions).selectinload(ChecklistVersion.checks))
    )
    if retailer_id is not None:
        stmt = stmt.where(Checklist.retailer_id == retailer_id)
    if vertical_id is not None:
        stmt = stmt.where(Checklist.vertical_id == vertical_id)
    return list(db.scalars(stmt))


def get_checklist(db: Session, checklist_id: int) -> Checklist | None:
    stmt = (
        select(Checklist)
        .where(Checklist.id == checklist_id)
        .options(selectinload(Checklist.versions).selectinload(ChecklistVersion.checks))
    )
    return db.scalars(stmt).first()


def get_version(db: Session, version_id: int) -> ChecklistVersion | None:
    stmt = (
        select(ChecklistVersion)
        .where(ChecklistVersion.id == version_id)
        .options(selectinload(ChecklistVersion.checks))
    )
    return db.scalars(stmt).first()


def versions_for_retailer_vertical(
    db: Session, retailer_id: int, vertical_id: int
) -> list[ChecklistVersion]:
    """Every version (any status) for a retailer/vertical pair.

    Filtering to published-and-effective is the resolver's job, not the
    repository's, so the rule stays in one place.
    """
    stmt = (
        select(ChecklistVersion)
        .join(Checklist)
        .where(Checklist.retailer_id == retailer_id)
        .where(Checklist.vertical_id == vertical_id)
        .where(Checklist.active.is_(True))
        .options(selectinload(ChecklistVersion.checks))
        .order_by(ChecklistVersion.version_number)
    )
    return list(db.scalars(stmt))


def next_version_number(db: Session, checklist_id: int) -> int:
    existing = db.scalars(
        select(ChecklistVersion.version_number).where(ChecklistVersion.checklist_id == checklist_id)
    ).all()
    return (max(existing) + 1) if existing else 1


def get_check(db: Session, check_id: int) -> CheckDefinition | None:
    return db.get(CheckDefinition, check_id)
