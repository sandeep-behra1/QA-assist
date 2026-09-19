from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class QueueItemOut(BaseModel):
    lead_id: int
    scoring_run_id: int
    retailer_name: str
    vertical_code: str
    agent_name: str | None
    call_datetime: datetime
    gate_result: str
    machine_gate_result: str | None
    reason: str
    critical_fail_count: int
    critical_uncertain_count: int
    incomplete_count: int
    priority: int
    qa_score_weighted: float | None


class HumanReviewOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    lead_id: int
    scoring_run_id: int
    status: str
    opened_by: str
    opened_at: datetime
    closed_at: datetime | None
    notes: str


class OpenReviewRequest(BaseModel):
    actor: str = "qa.reviewer@example.com"
