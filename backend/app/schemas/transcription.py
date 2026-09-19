from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.schemas.transcript import TranscriptSegmentOut


class ProviderOut(BaseModel):
    key: str
    label: str
    model: str | None
    ready: bool
    note: str | None = None


class TranscriptionJobOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    status: str
    provider: str
    model: str | None
    language: str
    diarization: str
    audio_filename: str
    audio_size_bytes: int
    duration_seconds: float | None
    channels: int | None
    latency_ms: float | None
    warnings: list[str]
    error: str | None
    lead_id: int | None
    created_at: datetime
    segments: list[TranscriptSegmentOut]


class AttachRequest(BaseModel):
    lead_id: int


class TranscribeRequest(BaseModel):
    provider: str | None = None
