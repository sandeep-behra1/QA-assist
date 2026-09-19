from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.core.enums import TranscriptSource


class TranscriptSegmentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    segment_id: int
    speaker: str
    start_time: float
    end_time: float
    text: str
    asr_confidence: float | None


class TranscriptOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int = Field(serialization_alias="transcript_id")
    lead_id: int
    call_id: int | None
    source: str
    language: str
    created_at: datetime
    segments: list[TranscriptSegmentOut]


class TranscriptUpload(BaseModel):
    """Accepts either the canonical JSON contract or pasted "SPEAKER: text" lines."""

    payload: dict | None = None
    pasted_text: str | None = None
    source: TranscriptSource = TranscriptSource.MANUAL_UPLOAD
    language: str = "en-AU"

    @model_validator(mode="after")
    def _require_one(self) -> TranscriptUpload:
        if bool(self.payload) == bool(self.pasted_text):
            raise ValueError("Provide exactly one of 'payload' or 'pasted_text'.")
        return self
