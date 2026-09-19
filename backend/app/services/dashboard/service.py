"""Dashboard aggregation."""

from __future__ import annotations

from collections import defaultdict

from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from app.core.enums import CheckStatus, GateDecision, ReviewStatus
from app.models import CheckResult, HumanReview, Lead
from app.repositories import scoring as scoring_repo


def build_dashboard_summary(db: Session, limit_activity: int = 12) -> dict:
    lead_ids = list(db.scalars(select(Lead.id)))
    latest_runs = scoring_repo.latest_runs_for_leads(db, lead_ids)

    counts = defaultdict(int)
    scores: list[float] = []
    machine_approved = 0

    for run in latest_runs.values():
        gate = run.effective_gate_result
        if gate:
            counts[gate] += 1
        if run.gate_result == GateDecision.APPROVED.value:
            machine_approved += 1
        if run.qa_score_weighted is not None:
            scores.append(run.qa_score_weighted)

    scored = len(latest_runs)
    total = len(lead_ids)

    pending_reviews = (
        db.scalar(
            select(func.count(HumanReview.id)).where(HumanReview.status == ReviewStatus.OPEN.value)
        )
        or 0
    )

    critical_fail_runs = sum(
        1
        for run in latest_runs.values()
        if any(
            r.critical and r.effective_status == CheckStatus.FAIL.value for r in run.check_results
        )
    )

    return {
        "total_sales": total,
        "scored_sales": scored,
        "approved": counts[GateDecision.APPROVED.value],
        "hold": counts[GateDecision.HOLD.value],
        "needs_human_review": counts[GateDecision.HUMAN_REVIEW.value],
        "pending_reviews": pending_reviews,
        "unscored": total - scored,
        "first_pass_yield_percent": (
            round(machine_approved / scored * 100, 1) if scored else None
        ),
        "critical_fail_rate_percent": (
            round(critical_fail_runs / scored * 100, 1) if scored else None
        ),
        "average_qa_score": round(sum(scores) / len(scores), 1) if scores else None,
        "top_failing_checks": _top_failing_checks(db),
        "recent_activity": _recent_activity(db, limit_activity),
    }


def _top_failing_checks(db: Session, limit: int = 6) -> list[dict]:
    """Checks that most often fail or come back uncertain, across latest runs."""
    lead_ids = list(db.scalars(select(Lead.id)))
    latest_runs = scoring_repo.latest_runs_for_leads(db, lead_ids)
    run_ids = [run.id for run in latest_runs.values()]
    if not run_ids:
        return []

    rows = db.execute(
        select(
            CheckResult.check_code,
            CheckResult.check_name,
            CheckResult.critical,
            func.sum(case((CheckResult.status == CheckStatus.FAIL.value, 1), else_=0)).label("fails"),
            func.sum(case((CheckResult.status == CheckStatus.UNCERTAIN.value, 1), else_=0)).label(
                "uncertains"
            ),
        )
        .where(CheckResult.scoring_run_id.in_(run_ids))
        .group_by(CheckResult.check_code, CheckResult.check_name, CheckResult.critical)
    ).all()

    summaries = [
        {
            "check_code": row.check_code,
            "check_name": row.check_name,
            "critical": bool(row.critical),
            "fail_count": int(row.fails or 0),
            "uncertain_count": int(row.uncertains or 0),
        }
        for row in rows
        if (row.fails or 0) or (row.uncertains or 0)
    ]
    summaries.sort(key=lambda item: (item["fail_count"] + item["uncertain_count"]), reverse=True)
    return summaries[:limit]


_ACTIVITY_SUMMARIES = {
    "SCORING_COMPLETED": "Scoring completed",
    "SALE_APPROVED": "Sale approved",
    "SALE_HOLD": "Sale on hold",
    "SALE_ROUTED_TO_REVIEW": "Routed to human review",
    "CHECK_OVERRIDDEN": "Check overridden",
    "LEAD_CREATED": "Lead created",
    "TRANSCRIPT_UPLOADED": "Transcript uploaded",
    "AUDIO_UPLOADED": "Audio uploaded",
    "CHECKLIST_VERSION_PUBLISHED": "Checklist version published",
    "HUMAN_REVIEW_OPENED": "Human review opened",
}


def _recent_activity(db: Session, limit: int) -> list[dict]:
    events = scoring_repo.list_audit_events(db, limit=limit)
    activity = []
    for event in events:
        summary = _ACTIVITY_SUMMARIES.get(event.event_type, event.event_type.replace("_", " ").title())
        detail = event.details or {}
        if event.event_type == "CHECK_OVERRIDDEN" and detail.get("check_name"):
            summary = f"{summary}: {detail['check_name']}"
        elif event.event_type == "SCORING_COMPLETED" and detail.get("gate_result"):
            summary = f"{summary} ({detail['gate_result']})"
        activity.append(
            {
                "lead_id": event.lead_id,
                "event_type": event.event_type,
                "actor": event.actor,
                "created_at": event.created_at,
                "summary": summary,
            }
        )
    return activity
