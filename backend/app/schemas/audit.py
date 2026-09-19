from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class AuditEventOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    event_type: str
    entity_type: str
    entity_id: str
    lead_id: int | None
    actor: str
    details: dict
    created_at: datetime
