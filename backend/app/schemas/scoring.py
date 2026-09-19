from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.core.enums import CheckStatus, OverrideReasonCode


class EvidenceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    transcript_id: int
    segment_id: int
    speaker: str
    text: str
    start_time: float
    end_time: float
    asr_confidence: float | None
    extraction_method: str


class HumanOverrideOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    check_result_id: int
    original_status: str
    override_status: str
    reason_code: str
    notes: str
    actor: str
    created_at: datetime


class CheckResultOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    scoring_run_id: int
    check_definition_id: int | None
    check_code: str
    check_name: str
    check_type: str
    evaluation_method: str
    critical: bool
    blocking_behavior: str
    weight: float
    display_order: int
    rule_version: str

    # The machine's verdict, never rewritten by an override.
    status: str
    # What the gate actually used (override if one exists).
    effective_status: str
    execution_status: str
    confidence_level: str | None
    reason: str
    observed_value: str | None
    expected_value: str | None
    llm_metadata: dict
    created_at: datetime

    evidence: list[EvidenceOut] = []
    overrides: list[HumanOverrideOut] = []


class ScoringRunOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    lead_id: int
    checklist_version_id: int | None
    transcript_id: int | None
    status: str
    started_at: datetime
    completed_at: datetime | None

    gate_result: str | None
    override_gate_result: str | None
    effective_gate_result: str | None
    gate_reason: str

    qa_score_raw: float | None
    qa_score_weighted: float | None
    summary: dict
    evaluator_metadata: dict
    error_message: str | None

    checklist_name: str | None = None
    checklist_version_label: str | None = None
    checklist_effective_from: str | None = None

    check_results: list[CheckResultOut] = []


class ScoringRunSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    lead_id: int
    status: str
    started_at: datetime
    completed_at: datetime | None
    gate_result: str | None
    override_gate_result: str | None
    effective_gate_result: str | None
    qa_score_weighted: float | None
    checklist_version_id: int | None


class OverrideRequest(BaseModel):
    override_status: CheckStatus
    reason_code: OverrideReasonCode
    notes: str = Field(min_length=1, description="Mandatory free-text justification.")
    actor: str = "qa.reviewer@example.com"
