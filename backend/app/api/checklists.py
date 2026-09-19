"""Checklist configuration endpoints (draft -> edit -> publish)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.mappers import checklist_out, checklist_version_out
from app.db.session import get_db
from app.models import Checklist
from app.repositories import checklists as checklist_repo
from app.schemas.checklist import (
    CheckDefinitionCreate,
    CheckDefinitionOut,
    CheckDefinitionUpdate,
    ChecklistCreate,
    ChecklistOut,
    ChecklistVersionOut,
    DraftVersionCreate,
    PublishRequest,
)
from app.services.rules.authoring import (
    ChecklistImmutableError,
    ChecklistValidationError,
    add_check,
    create_draft_version,
    delete_check,
    publish_version,
    update_check,
)

router = APIRouter(tags=["checklists"])


def _handle(exc: Exception) -> HTTPException:
    if isinstance(exc, ChecklistImmutableError):
        return HTTPException(status_code=409, detail=str(exc))
    return HTTPException(status_code=422, detail=str(exc))


@router.get("/checklists", response_model=list[ChecklistOut])
def list_checklists(
    retailer_id: int | None = None, vertical_id: int | None = None, db: Session = Depends(get_db)
) -> list[ChecklistOut]:
    return [
        checklist_out(c)
        for c in checklist_repo.list_checklists(db, retailer_id=retailer_id, vertical_id=vertical_id)
    ]


@router.post("/checklists", response_model=ChecklistOut, status_code=201)
def create_checklist(payload: ChecklistCreate, db: Session = Depends(get_db)) -> ChecklistOut:
    checklist = Checklist(**payload.model_dump())
    db.add(checklist)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="That checklist already exists.") from exc
    db.refresh(checklist)
    return checklist_out(checklist)


@router.get("/checklists/{checklist_id}", response_model=ChecklistOut)
def get_checklist(checklist_id: int, db: Session = Depends(get_db)) -> ChecklistOut:
    checklist = checklist_repo.get_checklist(db, checklist_id)
    if checklist is None:
        raise HTTPException(status_code=404, detail=f"Checklist {checklist_id} was not found.")
    return checklist_out(checklist)


@router.post("/checklists/{checklist_id}/versions", response_model=ChecklistVersionOut, status_code=201)
def create_version(
    checklist_id: int, payload: DraftVersionCreate, db: Session = Depends(get_db)
) -> ChecklistVersionOut:
    try:
        version = create_draft_version(
            db,
            checklist_id=checklist_id,
            copy_from_version_id=payload.copy_from_version_id,
            notes=payload.notes,
            actor="ui",
        )
    except ChecklistValidationError as exc:
        raise _handle(exc) from exc
    return checklist_version_out(version)


@router.get("/checklist-versions/{version_id}", response_model=ChecklistVersionOut)
def get_version(version_id: int, db: Session = Depends(get_db)) -> ChecklistVersionOut:
    version = checklist_repo.get_version(db, version_id)
    if version is None:
        raise HTTPException(status_code=404, detail=f"Checklist version {version_id} was not found.")
    return checklist_version_out(version)


@router.post("/checklist-versions/{version_id}/checks", response_model=CheckDefinitionOut, status_code=201)
def create_check(
    version_id: int, payload: CheckDefinitionCreate, db: Session = Depends(get_db)
) -> CheckDefinitionOut:
    data = payload.model_dump()
    for field in ("check_type", "evaluation_method", "evidence_source", "blocking_behavior"):
        data[field] = data[field].value if hasattr(data[field], "value") else data[field]
    try:
        check = add_check(db, version_id=version_id, payload=data, actor="ui")
    except (ChecklistImmutableError, ChecklistValidationError) as exc:
        raise _handle(exc) from exc
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=409, detail=f"Check code '{payload.code}' already exists in this version."
        ) from exc
    return CheckDefinitionOut.model_validate(check)


@router.patch("/checks/{check_id}", response_model=CheckDefinitionOut)
def patch_check(
    check_id: int, payload: CheckDefinitionUpdate, db: Session = Depends(get_db)
) -> CheckDefinitionOut:
    data = {}
    for field, value in payload.model_dump(exclude_unset=True).items():
        if value is None:
            continue
        data[field] = value.value if hasattr(value, "value") else value
    try:
        check = update_check(db, check_id=check_id, payload=data, actor="ui")
    except (ChecklistImmutableError, ChecklistValidationError) as exc:
        raise _handle(exc) from exc
    return CheckDefinitionOut.model_validate(check)


@router.delete("/checks/{check_id}", status_code=204, response_class=Response)
def remove_check(check_id: int, db: Session = Depends(get_db)) -> Response:
    try:
        delete_check(db, check_id=check_id)
    except (ChecklistImmutableError, ChecklistValidationError) as exc:
        raise _handle(exc) from exc
    return Response(status_code=204)


@router.post("/checklist-versions/{version_id}/publish", response_model=ChecklistVersionOut)
def publish(
    version_id: int, payload: PublishRequest, db: Session = Depends(get_db)
) -> ChecklistVersionOut:
    try:
        version = publish_version(
            db, version_id=version_id, effective_from=payload.effective_from, actor=payload.actor
        )
    except (ChecklistImmutableError, ChecklistValidationError) as exc:
        raise _handle(exc) from exc
    return checklist_version_out(version)
