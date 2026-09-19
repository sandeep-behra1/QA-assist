"""Audit event recording.

Append-only. Every material transition -- lead created, audio uploaded,
checklist published, scoring completed, sale on hold, check overridden --
lands here so the "why did this sale ship?" question is answerable from the
database alone.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy.orm import Session

from app.core.enums import AuditEventType
from app.models import AuditEvent


def json_safe(value: Any) -> Any:
    """Coerce values into something the JSON column can always store."""
    if isinstance(value, dict):
        return {str(k): json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [json_safe(v) for v in value]
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


def record_event(
    db: Session,
    *,
    event_type: AuditEventType | str,
    entity_type: str,
    entity_id: str | int,
    actor: str,
    details: dict | None = None,
    lead_id: int | None = None,
) -> AuditEvent:
    event = AuditEvent(
        event_type=str(event_type.value if isinstance(event_type, AuditEventType) else event_type),
        entity_type=entity_type,
        entity_id=str(entity_id),
        lead_id=lead_id,
        actor=actor,
        details=json_safe(details or {}),
    )
    db.add(event)
    db.flush()
    return event
