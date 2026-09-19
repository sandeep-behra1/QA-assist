from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field

from app.core.enums import LeadStatus


class LeadCreate(BaseModel):
    """Create a sale.

    ``attributes`` carries vertical-specific CRM fields (NMI, fuel type,
    life support, loan term...) so a new retailer field never requires a
    migration or a code change.
    """

    lead_id: int | None = Field(
        default=None, description="Optional explicit CRM id; generated when omitted."
    )
    vertical_id: int
    retailer_id: int
    plan_id: int | None = None
    agent_id: int | None = None
    team_leader_id: int | None = None
    campaign: str | None = None
    site: str | None = None
    call_datetime: datetime

    customer_name: str | None = None
    customer_email: str | None = None
    customer_phone: str | None = None
    customer_dob: date | None = None
    address_line1: str | None = None
    suburb: str | None = None
    state: str | None = None
    postcode: str | None = None

    attributes: dict = {}
    status: LeadStatus = LeadStatus.DRAFT


class LeadUpdate(BaseModel):
    plan_id: int | None = None
    agent_id: int | None = None
    team_leader_id: int | None = None
    campaign: str | None = None
    site: str | None = None
    call_datetime: datetime | None = None
    customer_name: str | None = None
    customer_email: str | None = None
    customer_phone: str | None = None
    customer_dob: date | None = None
    address_line1: str | None = None
    suburb: str | None = None
    state: str | None = None
    postcode: str | None = None
    attributes: dict | None = None
    status: LeadStatus | None = None


class CallOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    lead_id: int
    audio_filename: str | None
    audio_content_type: str | None
    audio_size_bytes: int | None
    duration_seconds: float | None
    transcription_status: str
    uploaded_at: datetime
    has_audio: bool = False


class LeadSummary(BaseModel):
    id: int
    vertical_code: str
    retailer_name: str
    plan_name: str | None
    agent_name: str | None
    team_leader_name: str | None
    campaign: str | None
    site: str | None
    call_datetime: datetime
    customer_name: str | None
    status: str
    gate_result: str | None
    machine_gate_result: str | None
    qa_score_weighted: float | None
    scored_at: datetime | None
    has_transcript: bool
    has_audio: bool


class LeadDetail(LeadSummary):
    vertical_id: int
    retailer_id: int
    plan_id: int | None
    agent_id: int | None
    team_leader_id: int | None
    customer_email: str | None
    customer_phone: str | None
    customer_dob: date | None
    address_line1: str | None
    suburb: str | None
    state: str | None
    postcode: str | None
    attributes: dict
    call: CallOut | None
    latest_scoring_run_id: int | None
