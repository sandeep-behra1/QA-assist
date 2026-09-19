from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class FailingCheck(BaseModel):
    check_code: str
    check_name: str
    fail_count: int
    uncertain_count: int
    critical: bool


class RecentActivity(BaseModel):
    lead_id: int | None
    event_type: str
    actor: str
    created_at: datetime
    summary: str


class DashboardSummary(BaseModel):
    total_sales: int
    scored_sales: int
    approved: int
    hold: int
    needs_human_review: int
    pending_reviews: int
    unscored: int
    # Share of scored sales that were approved by the machine with no human
    # intervention -- the headline "did QA get out of the way?" number.
    first_pass_yield_percent: float | None
    critical_fail_rate_percent: float | None
    average_qa_score: float | None
    top_failing_checks: list[FailingCheck]
    recent_activity: list[RecentActivity]
