"""Human review and overrides.

An override is an additional, additive record -- it never updates the
CheckResult's machine status. Original result, override result, reason code,
free-text notes, actor and timestamp are all retained together.
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, DateTime, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.enums import ReviewStatus
from app.db.base import Base
from app.db.types import BigIntPK

if TYPE_CHECKING:
    from app.models.scoring import CheckResult


class HumanReview(Base):
    __tablename__ = "human_reviews"

    id: Mapped[int] = mapped_column(BigIntPK, primary_key=True, autoincrement=True)
    lead_id: Mapped[int] = mapped_column(ForeignKey("leads.id", ondelete="CASCADE"), nullable=False)
    scoring_run_id: Mapped[int] = mapped_column(
        ForeignKey("scoring_runs.id", ondelete="CASCADE"), nullable=False
    )
    status: Mapped[str] = mapped_column(String(20), default=ReviewStatus.OPEN.value, nullable=False)
    opened_by: Mapped[str] = mapped_column(String(160), nullable=False)
    opened_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    notes: Mapped[str] = mapped_column(Text, default="", nullable=False)


class HumanOverride(Base):
    __tablename__ = "human_overrides"

    id: Mapped[int] = mapped_column(BigIntPK, primary_key=True, autoincrement=True)
    check_result_id: Mapped[int] = mapped_column(
        ForeignKey("check_results.id", ondelete="CASCADE"), nullable=False
    )
    # Copied at override time so the machine verdict survives even if the
    # CheckResult row were ever migrated or reshaped.
    original_status: Mapped[str] = mapped_column(String(20), nullable=False)
    override_status: Mapped[str] = mapped_column(String(20), nullable=False)
    reason_code: Mapped[str] = mapped_column(String(40), nullable=False)
    notes: Mapped[str] = mapped_column(Text, nullable=False)
    actor: Mapped[str] = mapped_column(String(160), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    check_result: Mapped[CheckResult] = relationship(back_populates="overrides")
