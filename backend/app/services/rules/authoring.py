"""Checklist authoring: draft -> edit -> publish.

Publishing is a one-way door. Once a version is PUBLISHED its rules are
frozen, because scored history must stay explainable: a call scored in
August has to be re-explainable with exactly the rules that applied then.
Changing the rules means creating a new draft, not editing the past.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

from sqlalchemy.orm import Session

from app.core.enums import AuditEventType, ChecklistVersionStatus
from app.models import CheckDefinition, Checklist, ChecklistVersion
from app.repositories import checklists as checklist_repo
from app.services.audit import record_event


class ChecklistImmutableError(RuntimeError):
    """Raised on any attempt to modify a published version."""


class ChecklistValidationError(ValueError):
    pass


def _assert_draft(version: ChecklistVersion) -> None:
    if version.status != ChecklistVersionStatus.DRAFT.value:
        raise ChecklistImmutableError(
            f"Checklist version {version.id} is {version.status} and cannot be modified. "
            "Create a new draft version instead."
        )


def create_draft_version(
    db: Session,
    *,
    checklist_id: int,
    copy_from_version_id: int | None = None,
    notes: str = "",
    actor: str = "system",
) -> ChecklistVersion:
    checklist = db.get(Checklist, checklist_id)
    if checklist is None:
        raise ChecklistValidationError(f"Checklist {checklist_id} was not found.")

    version = ChecklistVersion(
        checklist_id=checklist_id,
        version_number=checklist_repo.next_version_number(db, checklist_id),
        status=ChecklistVersionStatus.DRAFT.value,
        notes=notes,
    )
    db.add(version)
    db.flush()

    if copy_from_version_id is not None:
        source = checklist_repo.get_version(db, copy_from_version_id)
        if source is None:
            raise ChecklistValidationError(f"Source version {copy_from_version_id} was not found.")
        for check in source.checks:
            db.add(_clone_check(check, version.id))
        db.flush()

    record_event(
        db,
        event_type=AuditEventType.CHECKLIST_DRAFT_CREATED,
        entity_type="checklist_version",
        entity_id=version.id,
        actor=actor,
        details={
            "checklist_id": checklist_id,
            "version_number": version.version_number,
            "copied_from": copy_from_version_id,
        },
    )
    db.commit()
    db.refresh(version)
    return version


def _clone_check(check: CheckDefinition, version_id: int) -> CheckDefinition:
    return CheckDefinition(
        checklist_version_id=version_id,
        code=check.code,
        name=check.name,
        description=check.description,
        check_type=check.check_type,
        evaluation_method=check.evaluation_method,
        evidence_source=check.evidence_source,
        expected_source=check.expected_source,
        critical=check.critical,
        active=check.active,
        display_order=check.display_order,
        blocking_behavior=check.blocking_behavior,
        weight=check.weight,
        evaluation_config=dict(check.evaluation_config or {}),
        applicable_conditions=dict(check.applicable_conditions or {}),
    )


def add_check(db: Session, *, version_id: int, payload: dict, actor: str = "system") -> CheckDefinition:
    version = checklist_repo.get_version(db, version_id)
    if version is None:
        raise ChecklistValidationError(f"Checklist version {version_id} was not found.")
    _assert_draft(version)

    check = CheckDefinition(checklist_version_id=version_id, **payload)
    db.add(check)
    db.commit()
    db.refresh(check)
    # Sessions do not expire on commit, so the parent's cached collection
    # would otherwise still look empty to the next caller.
    db.expire(version, ["checks"])
    return check


def update_check(db: Session, *, check_id: int, payload: dict, actor: str = "system") -> CheckDefinition:
    check = checklist_repo.get_check(db, check_id)
    if check is None:
        raise ChecklistValidationError(f"Check {check_id} was not found.")
    _assert_draft(check.checklist_version)

    for field, value in payload.items():
        setattr(check, field, value)
    db.commit()
    db.refresh(check)
    return check


def delete_check(db: Session, *, check_id: int) -> None:
    check = checklist_repo.get_check(db, check_id)
    if check is None:
        raise ChecklistValidationError(f"Check {check_id} was not found.")
    version = check.checklist_version
    _assert_draft(version)
    db.delete(check)
    db.commit()
    db.expire(version, ["checks"])


def publish_version(
    db: Session,
    *,
    version_id: int,
    effective_from: date,
    actor: str = "system",
) -> ChecklistVersion:
    """Publish a draft, closing the previous version's window the day before.

    Windows are kept contiguous and non-overlapping so that every call date
    resolves to exactly one version.
    """
    version = checklist_repo.get_version(db, version_id)
    if version is None:
        raise ChecklistValidationError(f"Checklist version {version_id} was not found.")
    if version.status == ChecklistVersionStatus.PUBLISHED.value:
        raise ChecklistImmutableError(f"Checklist version {version_id} is already published.")
    if not version.checks:
        raise ChecklistValidationError("A checklist version must contain at least one check.")

    siblings = [
        v
        for v in checklist_repo.get_checklist(db, version.checklist_id).versions
        if v.id != version.id and v.status == ChecklistVersionStatus.PUBLISHED.value
    ]
    for previous in siblings:
        if previous.effective_from and previous.effective_from >= effective_from:
            raise ChecklistValidationError(
                f"Effective date {effective_from.isoformat()} overlaps published version "
                f"v{previous.version_number} (effective {previous.effective_from.isoformat()})."
            )
        if previous.effective_to is None:
            previous.effective_to = effective_from - timedelta(days=1)

    version.status = ChecklistVersionStatus.PUBLISHED.value
    version.effective_from = effective_from
    version.effective_to = None
    version.published_at = datetime.now(UTC)
    version.published_by = actor

    record_event(
        db,
        event_type=AuditEventType.CHECKLIST_VERSION_PUBLISHED,
        entity_type="checklist_version",
        entity_id=version.id,
        actor=actor,
        details={
            "checklist_id": version.checklist_id,
            "version_number": version.version_number,
            "effective_from": effective_from.isoformat(),
            "check_count": len(version.checks),
        },
    )
    db.commit()
    db.refresh(version)
    return version
