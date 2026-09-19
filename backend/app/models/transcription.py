"""Transcription jobs.

A job exists BEFORE the sale does: the intake flow is "upload audio ->
transcribe -> fill in the sale details -> save", so the staged audio and the
canonical transcript it produced need somewhere durable to live until they are
attached to a lead. Persisting them (rather than holding them in the browser or
in process memory) also gives an audit trail of what each provider returned.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.enums import DiarizationMode, TranscriptionJobStatus
from app.db.base import Base
from app.db.types import FlexibleJSON


class TranscriptionJob(Base):
    __tablename__ = "transcription_jobs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    status: Mapped[str] = mapped_column(
        String(20), default=TranscriptionJobStatus.COMPLETED.value, nullable=False
    )
    provider: Mapped[str] = mapped_column(String(40), nullable=False)
    model: Mapped[str | None] = mapped_column(String(80), nullable=True)
    language: Mapped[str] = mapped_column(String(20), default="en-AU", nullable=False)
    diarization: Mapped[str] = mapped_column(
        String(20), default=DiarizationMode.NONE.value, nullable=False
    )

    audio_storage_key: Mapped[str] = mapped_column(String(500), nullable=False)
    audio_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    audio_content_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    audio_size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    duration_seconds: Mapped[float | None] = mapped_column(Float, nullable=True)
    channels: Mapped[int | None] = mapped_column(Integer, nullable=True)

    latency_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    warnings: Mapped[list] = mapped_column(FlexibleJSON, default=list, nullable=False)
    # Canonical segments: [{segment_id, speaker, start_time, end_time, text, asr_confidence}]
    segments: Mapped[list] = mapped_column(FlexibleJSON, default=list, nullable=False)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)

    lead_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("leads.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    attached_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
