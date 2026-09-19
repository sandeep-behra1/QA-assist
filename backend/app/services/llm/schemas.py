"""The only shape an LLM is allowed to return.

Note what is absent: no gate decision, no criticality, no rule version, no
authoritative value. The model may say what it thinks the transcript shows
and which segments show it -- nothing more.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.core.enums import ConfidenceLevel


class StructuredInterpretation(BaseModel):
    model_config = ConfigDict(frozen=True, extra="ignore")

    decision: str = Field(description="PASS | FAIL | UNCERTAIN")
    confidence_level: ConfidenceLevel
    evidence_segment_ids: list[int] = Field(default_factory=list)
    observed_value: str | None = None
    reason: str = ""

    @field_validator("decision")
    @classmethod
    def _validate_decision(cls, value: str) -> str:
        normalized = value.strip().upper()
        if normalized not in {"PASS", "FAIL", "UNCERTAIN"}:
            raise ValueError(f"decision must be PASS, FAIL or UNCERTAIN (got {value!r})")
        return normalized

    @field_validator("confidence_level", mode="before")
    @classmethod
    def _coerce_confidence(cls, value: object) -> object:
        if isinstance(value, str):
            return value.strip().upper()
        return value


class InterpreterCall(BaseModel):
    """Traceability record for a single interpreter invocation."""

    model_config = ConfigDict(frozen=True)

    provider: str
    model: str
    prompt_version: str
    evaluation_method: str
    latency_ms: float
    succeeded: bool
    error: str | None = None
