"""Lead application service: create and update sales, with audit."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.enums import AuditEventType, LeadStatus
from app.models import Lead, Plan, Retailer, RetailerVertical, Vertical
from app.repositories import leads as leads_repo
from app.services.audit import record_event


class LeadValidationError(ValueError):
    pass


class LeadNotFoundError(LookupError):
    pass


def _validate_references(db: Session, *, vertical_id: int, retailer_id: int, plan_id: int | None) -> None:
    if db.get(Vertical, vertical_id) is None:
        raise LeadValidationError(f"Vertical {vertical_id} does not exist.")
    if db.get(Retailer, retailer_id) is None:
        raise LeadValidationError(f"Retailer {retailer_id} does not exist.")

    link = db.scalar(
        select(RetailerVertical)
        .where(RetailerVertical.retailer_id == retailer_id)
        .where(RetailerVertical.vertical_id == vertical_id)
    )
    if link is None:
        raise LeadValidationError("That retailer does not trade in the selected vertical.")

    if plan_id is not None:
        plan = db.get(Plan, plan_id)
        if plan is None:
            raise LeadValidationError(f"Plan {plan_id} does not exist.")
        if plan.retailer_id != retailer_id:
            raise LeadValidationError("The selected plan does not belong to that retailer.")


def create_lead(db: Session, payload: dict, actor: str = "system") -> Lead:
    _validate_references(
        db,
        vertical_id=payload["vertical_id"],
        retailer_id=payload["retailer_id"],
        plan_id=payload.get("plan_id"),
    )

    explicit_id = payload.pop("lead_id", None)
    if explicit_id is not None:
        if leads_repo.get_lead(db, explicit_id) is not None:
            raise LeadValidationError(f"Lead {explicit_id} already exists.")
        payload["id"] = explicit_id

    status = payload.get("status", LeadStatus.DRAFT)
    payload["status"] = status.value if hasattr(status, "value") else str(status)

    lead = Lead(**payload)
    leads_repo.create_lead(db, lead)

    record_event(
        db,
        event_type=AuditEventType.LEAD_CREATED,
        entity_type="lead",
        entity_id=lead.id,
        actor=actor,
        lead_id=lead.id,
        details={"retailer_id": lead.retailer_id, "vertical_id": lead.vertical_id, "status": lead.status},
    )
    db.commit()
    db.refresh(lead)
    return lead


def update_lead(db: Session, lead_id: int, payload: dict, actor: str = "system") -> Lead:
    lead = leads_repo.get_lead(db, lead_id)
    if lead is None:
        raise LeadNotFoundError(f"Lead {lead_id} was not found.")

    changes: dict[str, object] = {}
    for field, value in payload.items():
        if value is None:
            continue
        if field == "status":
            value = value.value if hasattr(value, "value") else str(value)
        if getattr(lead, field) != value:
            changes[field] = value
            setattr(lead, field, value)

    if changes:
        _validate_references(
            db,
            vertical_id=lead.vertical_id,
            retailer_id=lead.retailer_id,
            plan_id=lead.plan_id,
        )
        record_event(
            db,
            event_type=AuditEventType.LEAD_UPDATED,
            entity_type="lead",
            entity_id=lead.id,
            actor=actor,
            lead_id=lead.id,
            details={"changed_fields": sorted(changes)},
        )
    db.commit()
    db.refresh(lead)
    return lead


def validate_lead_for_scoring(db: Session, lead_id: int) -> list[str]:
    """Pre-flight problems that would stop this sale being scored.

    Used by the "Validate Data" action so a user sees what is missing before
    they trigger scoring, instead of getting an error afterwards.
    """
    lead = leads_repo.get_lead(db, lead_id)
    if lead is None:
        raise LeadNotFoundError(f"Lead {lead_id} was not found.")

    problems: list[str] = []
    if lead.plan_id is None:
        problems.append("No plan selected, so rate-card checks cannot run.")
    if not lead.customer_email:
        problems.append("No CRM email, so the email match check will be UNCERTAIN.")
    if lead.customer_dob is None:
        problems.append("No CRM date of birth, so the DOB check will be UNCERTAIN.")
    if not lead.address_line1:
        problems.append("No CRM supply address, so the address check will be UNCERTAIN.")

    transcript = leads_repo.latest_transcript(db, lead_id)
    if transcript is None or not transcript.segments:
        problems.append("No transcript attached: this sale cannot be scored yet.")

    return problems
