from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field

from app.core.enums import BlockingBehavior, CheckType, EvaluationMethod, EvidenceSource


class CheckDefinitionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    checklist_version_id: int
    code: str
    name: str
    description: str
    check_type: str
    evaluation_method: str
    evidence_source: str
    expected_source: str | None
    critical: bool
    active: bool
    display_order: int
    blocking_behavior: str
    weight: float
    evaluation_config: dict
    applicable_conditions: dict


class CheckDefinitionCreate(BaseModel):
    code: str = Field(min_length=2, max_length=80)
    name: str = Field(min_length=2, max_length=200)
    description: str = ""
    check_type: CheckType
    evaluation_method: EvaluationMethod
    evidence_source: EvidenceSource = EvidenceSource.AGENT_TRANSCRIPT
    expected_source: str | None = None
    critical: bool = False
    active: bool = True
    display_order: int = 0
    blocking_behavior: BlockingBehavior = BlockingBehavior.NON_BLOCKING
    weight: float = 1.0
    evaluation_config: dict = {}
    applicable_conditions: dict = {}


class CheckDefinitionUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    check_type: CheckType | None = None
    evaluation_method: EvaluationMethod | None = None
    evidence_source: EvidenceSource | None = None
    expected_source: str | None = None
    critical: bool | None = None
    active: bool | None = None
    display_order: int | None = None
    blocking_behavior: BlockingBehavior | None = None
    weight: float | None = None
    evaluation_config: dict | None = None
    applicable_conditions: dict | None = None


class ChecklistVersionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    checklist_id: int
    version_number: int
    status: str
    effective_from: date | None
    effective_to: date | None
    notes: str
    published_at: datetime | None
    published_by: str | None
    checks: list[CheckDefinitionOut] = []
    check_count: int = 0
    critical_count: int = 0


class ChecklistOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    retailer_id: int
    vertical_id: int
    retailer_name: str | None = None
    vertical_code: str | None = None
    code: str
    name: str
    active: bool
    versions: list[ChecklistVersionOut] = []
    current_version: ChecklistVersionOut | None = None


class ChecklistCreate(BaseModel):
    retailer_id: int
    vertical_id: int
    code: str = Field(min_length=2, max_length=60)
    name: str = Field(min_length=2, max_length=200)


class DraftVersionCreate(BaseModel):
    copy_from_version_id: int | None = None
    notes: str = ""


class PublishRequest(BaseModel):
    effective_from: date
    actor: str = "qa.manager@example.com"
