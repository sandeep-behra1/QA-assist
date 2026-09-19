"""Checklists, their immutable published versions, and the data-driven rules.

A Checklist is a stable identity ("Origin Energy - Energy QA"). A
ChecklistVersion is a dated, publishable snapshot of its rules. Publishing
freezes a version: edits create a new DRAFT instead of mutating history, so
a call scored last month can always be re-explained with the exact rules
that applied to it.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.enums import BlockingBehavior, ChecklistVersionStatus
from app.db.base import Base, TimestampMixin
from app.db.types import FlexibleJSON

if TYPE_CHECKING:
    from app.models.catalog import Retailer, Vertical


class Checklist(Base, TimestampMixin):
    __tablename__ = "checklists"
    __table_args__ = (
        UniqueConstraint("retailer_id", "vertical_id", "code", name="uq_checklist_identity"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    retailer_id: Mapped[int] = mapped_column(ForeignKey("retailers.id", ondelete="CASCADE"), nullable=False)
    vertical_id: Mapped[int] = mapped_column(ForeignKey("verticals.id", ondelete="CASCADE"), nullable=False)
    code: Mapped[str] = mapped_column(String(60), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    retailer: Mapped[Retailer] = relationship(lazy="joined")
    vertical: Mapped[Vertical] = relationship(lazy="joined")
    versions: Mapped[list[ChecklistVersion]] = relationship(
        back_populates="checklist",
        cascade="all, delete-orphan",
        order_by="ChecklistVersion.version_number",
    )


class ChecklistVersion(Base, TimestampMixin):
    __tablename__ = "checklist_versions"
    __table_args__ = (
        UniqueConstraint("checklist_id", "version_number", name="uq_checklist_version_number"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    checklist_id: Mapped[int] = mapped_column(
        ForeignKey("checklists.id", ondelete="CASCADE"), nullable=False
    )
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), default=ChecklistVersionStatus.DRAFT.value, nullable=False
    )
    effective_from: Mapped[date | None] = mapped_column(Date, nullable=True)
    effective_to: Mapped[date | None] = mapped_column(Date, nullable=True)
    notes: Mapped[str] = mapped_column(String(500), default="", nullable=False)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    published_by: Mapped[str | None] = mapped_column(String(160), nullable=True)

    checklist: Mapped[Checklist] = relationship(back_populates="versions")
    checks: Mapped[list[CheckDefinition]] = relationship(
        back_populates="checklist_version",
        cascade="all, delete-orphan",
        order_by="CheckDefinition.display_order",
    )

    @property
    def is_published(self) -> bool:
        return self.status == ChecklistVersionStatus.PUBLISHED.value

    @property
    def label(self) -> str:
        return f"v{self.version_number}"


class CheckDefinition(Base, TimestampMixin):
    """One QA rule, expressed as data rather than code.

    ``evaluation_method`` selects the evaluator; ``expected_source`` names
    the authoritative field to compare against (e.g. "RATE_CARD.peak_rate");
    ``evaluation_config`` carries method-specific knobs (tolerance, required
    phrases, thresholds). Adding a retailer's new rule is an INSERT, not a
    deploy.
    """

    __tablename__ = "check_definitions"
    __table_args__ = (
        UniqueConstraint("checklist_version_id", "code", name="uq_check_code_per_version"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    checklist_version_id: Mapped[int] = mapped_column(
        ForeignKey("checklist_versions.id", ondelete="CASCADE"), nullable=False
    )

    code: Mapped[str] = mapped_column(String(80), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="", nullable=False)

    check_type: Mapped[str] = mapped_column(String(20), nullable=False)
    evaluation_method: Mapped[str] = mapped_column(String(30), nullable=False)
    evidence_source: Mapped[str] = mapped_column(String(30), nullable=False)
    expected_source: Mapped[str | None] = mapped_column(String(120), nullable=True)

    critical: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    display_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    blocking_behavior: Mapped[str] = mapped_column(
        String(20), default=BlockingBehavior.NON_BLOCKING.value, nullable=False
    )
    weight: Mapped[float] = mapped_column(Float, default=1.0, nullable=False)

    evaluation_config: Mapped[dict] = mapped_column(FlexibleJSON, default=dict, nullable=False)
    # e.g. {"lead.attributes.fuel_type": "ELECTRICITY"} -- when the lead does
    # not match, the check resolves to NOT_APPLICABLE instead of running.
    applicable_conditions: Mapped[dict] = mapped_column(FlexibleJSON, default=dict, nullable=False)

    checklist_version: Mapped[ChecklistVersion] = relationship(back_populates="checks")
