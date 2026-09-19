"""Lead (the sale + its CRM snapshot) and Call (the audio recording)."""

from __future__ import annotations

from datetime import date, datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    BigInteger,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Sequence,
    String,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.enums import LeadStatus, TranscriptionStatus
from app.db.base import Base, TimestampMixin
from app.db.types import BigIntPK, FlexibleJSON

if TYPE_CHECKING:
    from app.models.catalog import Agent, Plan, Retailer, TeamLeader, Vertical
    from app.models.scoring import ScoringRun
    from app.models.transcript import Transcript


class Lead(Base, TimestampMixin):
    """A completed sale awaiting QA.

    Core CRM fields that every vertical shares are real columns (so they can
    be indexed, filtered and compared deterministically). Everything
    vertical-specific -- NMI, fuel type, life support, loan term, policy
    excess -- lives in ``attributes`` so a new retailer field never needs a
    migration.
    """

    __tablename__ = "leads"

    id: Mapped[int] = mapped_column(BigIntPK, Sequence("lead_id_seq", start=3613790), primary_key=True)

    vertical_id: Mapped[int] = mapped_column(ForeignKey("verticals.id"), nullable=False)
    retailer_id: Mapped[int] = mapped_column(ForeignKey("retailers.id"), nullable=False)
    plan_id: Mapped[int | None] = mapped_column(ForeignKey("plans.id"), nullable=True)
    agent_id: Mapped[int | None] = mapped_column(ForeignKey("agents.id"), nullable=True)
    team_leader_id: Mapped[int | None] = mapped_column(ForeignKey("team_leaders.id"), nullable=True)

    campaign: Mapped[str | None] = mapped_column(String(60), nullable=True)
    site: Mapped[str | None] = mapped_column(String(60), nullable=True)
    call_datetime: Mapped[datetime] = mapped_column(DateTime(timezone=False), nullable=False)

    customer_name: Mapped[str | None] = mapped_column(String(160), nullable=True)
    customer_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    customer_phone: Mapped[str | None] = mapped_column(String(40), nullable=True)
    customer_dob: Mapped[date | None] = mapped_column(Date, nullable=True)
    address_line1: Mapped[str | None] = mapped_column(String(255), nullable=True)
    suburb: Mapped[str | None] = mapped_column(String(120), nullable=True)
    state: Mapped[str | None] = mapped_column(String(40), nullable=True)
    postcode: Mapped[str | None] = mapped_column(String(20), nullable=True)

    attributes: Mapped[dict] = mapped_column(FlexibleJSON, default=dict, nullable=False)

    status: Mapped[str] = mapped_column(String(20), default=LeadStatus.DRAFT.value, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    vertical: Mapped[Vertical] = relationship("Vertical", lazy="joined")
    retailer: Mapped[Retailer] = relationship("Retailer", lazy="joined")
    plan: Mapped[Plan | None] = relationship("Plan", lazy="joined")
    agent: Mapped[Agent | None] = relationship("Agent", lazy="joined")
    team_leader: Mapped[TeamLeader | None] = relationship("TeamLeader", lazy="joined")

    calls: Mapped[list[Call]] = relationship(
        back_populates="lead", cascade="all, delete-orphan", order_by="Call.id"
    )
    transcripts: Mapped[list[Transcript]] = relationship(
        "Transcript", back_populates="lead", cascade="all, delete-orphan", order_by="Transcript.id"
    )
    scoring_runs: Mapped[list[ScoringRun]] = relationship(
        "ScoringRun", back_populates="lead", cascade="all, delete-orphan", order_by="ScoringRun.id"
    )


class Call(Base):
    """A recorded call attached to a lead.

    Audio is stored through the FileStorage abstraction (local disk today,
    object storage later) -- only the storage key lives in the database.
    """

    __tablename__ = "calls"

    id: Mapped[int] = mapped_column(BigIntPK, Sequence("call_id_seq", start=7100452), primary_key=True)
    lead_id: Mapped[int] = mapped_column(ForeignKey("leads.id", ondelete="CASCADE"), nullable=False)

    audio_storage_key: Mapped[str | None] = mapped_column(String(500), nullable=True)
    audio_filename: Mapped[str | None] = mapped_column(String(255), nullable=True)
    audio_content_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    audio_size_bytes: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    duration_seconds: Mapped[float | None] = mapped_column(Float, nullable=True)

    transcription_status: Mapped[str] = mapped_column(
        String(20), default=TranscriptionStatus.NOT_STARTED.value, nullable=False
    )
    uploaded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    lead: Mapped[Lead] = relationship(back_populates="calls")
