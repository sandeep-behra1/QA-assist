"""The canonical transcript contract.

This schema is frozen and deliberately independent of whoever produced the
transcription. Manual upload today; Whisper/Deepgram/Azure/CIMET tomorrow --
the scoring engine only ever sees Transcript + TranscriptSegment, so adding
a provider requires no change below this layer.
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    BigInteger,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    Sequence,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.enums import TranscriptSource
from app.db.base import Base
from app.db.types import BigIntPK, FlexibleJSON

if TYPE_CHECKING:
    from app.models.lead import Call, Lead


class Transcript(Base):
    __tablename__ = "transcripts"

    id: Mapped[int] = mapped_column(
        BigIntPK, Sequence("transcript_id_seq", start=900124), primary_key=True
    )
    lead_id: Mapped[int] = mapped_column(ForeignKey("leads.id", ondelete="CASCADE"), nullable=False)
    call_id: Mapped[int | None] = mapped_column(ForeignKey("calls.id", ondelete="SET NULL"), nullable=True)

    source: Mapped[str] = mapped_column(
        String(30), default=TranscriptSource.MANUAL_UPLOAD.value, nullable=False
    )
    language: Mapped[str] = mapped_column(String(20), default="en-AU", nullable=False)
    provider_metadata: Mapped[dict] = mapped_column(FlexibleJSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    lead: Mapped[Lead] = relationship(back_populates="transcripts")
    call: Mapped[Call | None] = relationship()
    segments: Mapped[list[TranscriptSegment]] = relationship(
        back_populates="transcript",
        cascade="all, delete-orphan",
        order_by="TranscriptSegment.segment_id",
    )


class TranscriptSegment(Base):
    """One utterance.

    ``segment_id`` is the number the transcript itself uses (1, 2, 3...) and
    is what Evidence rows and LLM responses reference; ``id`` is the internal
    surrogate key. Keeping both means evidence references stay stable and
    human-readable while still being foreign-keyable.
    """

    __tablename__ = "transcript_segments"
    __table_args__ = (
        UniqueConstraint("transcript_id", "segment_id", name="uq_transcript_segment_number"),
    )

    id: Mapped[int] = mapped_column(BigIntPK, primary_key=True, autoincrement=True)
    transcript_id: Mapped[int] = mapped_column(
        ForeignKey("transcripts.id", ondelete="CASCADE"), nullable=False
    )
    segment_id: Mapped[int] = mapped_column(Integer, nullable=False)

    speaker: Mapped[str] = mapped_column(String(20), nullable=False)
    start_time: Mapped[float] = mapped_column(Float, nullable=False)
    end_time: Mapped[float] = mapped_column(Float, nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    # Transcription confidence only. Evaluation confidence is a separate
    # concept and lives on CheckResult.confidence_level.
    asr_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)

    transcript: Mapped[Transcript] = relationship(back_populates="segments")

    @property
    def duration(self) -> float:
        return self.end_time - self.start_time
