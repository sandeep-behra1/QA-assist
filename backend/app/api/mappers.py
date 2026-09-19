"""ORM -> API DTO mapping.

Kept out of the routes so route functions stay thin, and out of the
services so services never depend on API shapes.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.models import Checklist, ChecklistVersion, Lead, ScoringRun
from app.repositories import leads as leads_repo
from app.schemas.checklist import ChecklistOut, ChecklistVersionOut
from app.schemas.lead import CallOut, LeadDetail, LeadSummary
from app.schemas.scoring import ScoringRunOut


def lead_summary(lead: Lead, run: ScoringRun | None, *, has_transcript: bool, has_audio: bool) -> LeadSummary:
    return LeadSummary(
        id=lead.id,
        vertical_code=lead.vertical.code,
        retailer_name=lead.retailer.name,
        plan_name=lead.plan.name if lead.plan else None,
        agent_name=lead.agent.name if lead.agent else None,
        team_leader_name=lead.team_leader.name if lead.team_leader else None,
        campaign=lead.campaign,
        site=lead.site,
        call_datetime=lead.call_datetime,
        customer_name=lead.customer_name,
        status=lead.status,
        gate_result=run.effective_gate_result if run else None,
        machine_gate_result=run.gate_result if run else None,
        qa_score_weighted=run.qa_score_weighted if run else None,
        scored_at=run.completed_at if run else None,
        has_transcript=has_transcript,
        has_audio=has_audio,
    )


def lead_detail(db: Session, lead: Lead, run: ScoringRun | None) -> LeadDetail:
    transcript = leads_repo.latest_transcript(db, lead.id)
    call = lead.calls[0] if lead.calls else None

    base = lead_summary(
        lead,
        run,
        has_transcript=bool(transcript and transcript.segments),
        has_audio=bool(call and call.audio_storage_key),
    )
    return LeadDetail(
        **base.model_dump(),
        vertical_id=lead.vertical_id,
        retailer_id=lead.retailer_id,
        plan_id=lead.plan_id,
        agent_id=lead.agent_id,
        team_leader_id=lead.team_leader_id,
        customer_email=lead.customer_email,
        customer_phone=lead.customer_phone,
        customer_dob=lead.customer_dob,
        address_line1=lead.address_line1,
        suburb=lead.suburb,
        state=lead.state,
        postcode=lead.postcode,
        attributes=dict(lead.attributes or {}),
        call=call_out(call) if call else None,
        latest_scoring_run_id=run.id if run else None,
    )


def call_out(call) -> CallOut:
    return CallOut(
        id=call.id,
        lead_id=call.lead_id,
        audio_filename=call.audio_filename,
        audio_content_type=call.audio_content_type,
        audio_size_bytes=call.audio_size_bytes,
        duration_seconds=call.duration_seconds,
        transcription_status=call.transcription_status,
        uploaded_at=call.uploaded_at,
        has_audio=bool(call.audio_storage_key),
    )


def scoring_run_out(run: ScoringRun) -> ScoringRunOut:
    version = run.checklist_version
    payload = ScoringRunOut.model_validate(run)
    if version is not None:
        payload.checklist_version_label = f"v{version.version_number}"
        payload.checklist_effective_from = (
            version.effective_from.isoformat() if version.effective_from else None
        )
        payload.checklist_name = version.checklist.name if version.checklist else None
    return payload


def checklist_version_out(version: ChecklistVersion) -> ChecklistVersionOut:
    payload = ChecklistVersionOut.model_validate(version)
    payload.check_count = len(version.checks)
    payload.critical_count = sum(1 for check in version.checks if check.critical)
    return payload


def checklist_out(checklist: Checklist) -> ChecklistOut:
    versions = [checklist_version_out(v) for v in checklist.versions]
    published = [v for v in versions if v.status == "PUBLISHED" and v.effective_to is None]
    return ChecklistOut(
        id=checklist.id,
        retailer_id=checklist.retailer_id,
        vertical_id=checklist.vertical_id,
        retailer_name=checklist.retailer.name if checklist.retailer else None,
        vertical_code=checklist.vertical.code if checklist.vertical else None,
        code=checklist.code,
        name=checklist.name,
        active=checklist.active,
        versions=versions,
        current_version=published[-1] if published else None,
    )
