"""Scoring runs, check results and evidence.

ScoringRun rows are append-only: re-scoring a lead creates a new run rather
than mutating the last one, so the full history of what the system decided
and why stays intact. ``gate_result`` is the machine decision and is never
rewritten; ``override_gate_result`` records what the gate becomes once human
overrides are taken into account.
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.enums import CheckStatus, ExecutionStatus, ScoringRunStatus
from app.db.base import Base
from app.db.types import BigIntPK, FlexibleJSON

if TYPE_CHECKING:
    from app.models.checklist import CheckDefinition, ChecklistVersion
    from app.models.lead import Lead
    from app.models.review import HumanOverride
    from app.models.transcript import Transcript


class ScoringRun(Base):
    __tablename__ = "scoring_runs"

    id: Mapped[int] = mapped_column(BigIntPK, primary_key=True, autoincrement=True)
    lead_id: Mapped[int] = mapped_column(ForeignKey("leads.id", ondelete="CASCADE"), nullable=False)
    checklist_version_id: Mapped[int | None] = mapped_column(
        ForeignKey("checklist_versions.id"), nullable=True
    )
    transcript_id: Mapped[int | None] = mapped_column(ForeignKey("transcripts.id"), nullable=True)

    status: Mapped[str] = mapped_column(String(20), default=ScoringRunStatus.RUNNING.value, nullable=False)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # The deterministic machine decision. Immutable once written.
    gate_result: Mapped[str | None] = mapped_column(String(20), nullable=True)
    # Recomputed when a human override lands; null while no override exists.
    override_gate_result: Mapped[str | None] = mapped_column(String(20), nullable=True)
    gate_reason: Mapped[str] = mapped_column(Text, default="", nullable=False)

    # QA score is reported alongside the gate but never decides it.
    qa_score_raw: Mapped[float | None] = mapped_column(Float, nullable=True)
    qa_score_weighted: Mapped[float | None] = mapped_column(Float, nullable=True)

    summary: Mapped[dict] = mapped_column(FlexibleJSON, default=dict, nullable=False)
    evaluator_metadata: Mapped[dict] = mapped_column(FlexibleJSON, default=dict, nullable=False)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    lead: Mapped[Lead] = relationship(back_populates="scoring_runs")
    checklist_version: Mapped[ChecklistVersion | None] = relationship(lazy="joined")
    transcript: Mapped[Transcript | None] = relationship()
    check_results: Mapped[list[CheckResult]] = relationship(
        back_populates="scoring_run", cascade="all, delete-orphan", order_by="CheckResult.display_order"
    )

    @property
    def effective_gate_result(self) -> str | None:
        return self.override_gate_result or self.gate_result


class CheckResult(Base):
    __tablename__ = "check_results"

    id: Mapped[int] = mapped_column(BigIntPK, primary_key=True, autoincrement=True)
    scoring_run_id: Mapped[int] = mapped_column(
        ForeignKey("scoring_runs.id", ondelete="CASCADE"), nullable=False
    )
    check_definition_id: Mapped[int | None] = mapped_column(
        ForeignKey("check_definitions.id"), nullable=True
    )

    # Denormalised so a result stays readable even if the rule is later
    # superseded -- the audit story must not depend on joins to live config.
    check_code: Mapped[str] = mapped_column(String(80), nullable=False)
    check_name: Mapped[str] = mapped_column(String(200), nullable=False)
    check_type: Mapped[str] = mapped_column(String(20), nullable=False)
    evaluation_method: Mapped[str] = mapped_column(String(30), nullable=False)
    critical: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    blocking_behavior: Mapped[str] = mapped_column(String(20), nullable=False)
    weight: Mapped[float] = mapped_column(Float, default=1.0, nullable=False)
    display_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    rule_version: Mapped[str] = mapped_column(String(40), nullable=False)

    status: Mapped[str] = mapped_column(String(20), default=CheckStatus.UNCERTAIN.value, nullable=False)
    execution_status: Mapped[str] = mapped_column(
        String(20), default=ExecutionStatus.COMPLETED.value, nullable=False
    )
    confidence_level: Mapped[str | None] = mapped_column(String(10), nullable=True)
    reason: Mapped[str] = mapped_column(Text, default="", nullable=False)
    observed_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    expected_value: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Provider/model/prompt_version/latency when an LLM interpreted evidence.
    llm_metadata: Mapped[dict] = mapped_column(FlexibleJSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    scoring_run: Mapped[ScoringRun] = relationship(back_populates="check_results")
    check_definition: Mapped[CheckDefinition | None] = relationship()
    evidence: Mapped[list[Evidence]] = relationship(
        back_populates="check_result", cascade="all, delete-orphan", order_by="Evidence.id"
    )
    overrides: Mapped[list[HumanOverride]] = relationship(
        back_populates="check_result", cascade="all, delete-orphan", order_by="HumanOverride.id"
    )

    @property
    def latest_override(self) -> HumanOverride | None:
        return self.overrides[-1] if self.overrides else None

    @property
    def effective_status(self) -> str:
        """Status the gate should use: the human override if one exists.

        The machine ``status`` column is never modified by an override -- it
        stays exactly as the evaluator wrote it.
        """
        override = self.latest_override
        return override.override_status if override else self.status


class Evidence(Base):
    """A validated pointer into a real transcript segment.

    Every row is checked against the transcript before it is written (see
    services/evidence/validator.py), which is what stops an LLM from citing
    a segment that does not exist.
    """

    __tablename__ = "evidence"

    id: Mapped[int] = mapped_column(BigIntPK, primary_key=True, autoincrement=True)
    check_result_id: Mapped[int] = mapped_column(
        ForeignKey("check_results.id", ondelete="CASCADE"), nullable=False
    )
    transcript_id: Mapped[int] = mapped_column(ForeignKey("transcripts.id"), nullable=False)
    segment_id: Mapped[int] = mapped_column(Integer, nullable=False)

    speaker: Mapped[str] = mapped_column(String(20), nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    start_time: Mapped[float] = mapped_column(Float, nullable=False)
    end_time: Mapped[float] = mapped_column(Float, nullable=False)
    asr_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    extraction_method: Mapped[str] = mapped_column(String(30), nullable=False)

    check_result: Mapped[CheckResult] = relationship(back_populates="evidence")
