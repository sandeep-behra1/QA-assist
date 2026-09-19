"""Shared types and confidence policy for all evaluators."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

from app.core.config import Settings
from app.core.enums import CheckStatus, ConfidenceLevel, ExecutionStatus
from app.models import CheckDefinition, TranscriptSegment
from app.services.llm import EvidenceInterpreter

# Above this, transcription is treated as clean; between this and the
# configured floor it is usable but noted.
_MEDIUM_CONFIDENCE_ASR = 0.85


@dataclass(frozen=True)
class EvidenceRef:
    segment: TranscriptSegment
    extraction_method: str


@dataclass
class EvaluationContext:
    check: CheckDefinition
    segments: list[TranscriptSegment]
    authoritative_context: dict
    interpreter: EvidenceInterpreter
    settings: Settings
    reference_date: date | None = None


@dataclass
class EvaluationOutcome:
    status: CheckStatus
    reason: str
    execution_status: ExecutionStatus = ExecutionStatus.COMPLETED
    confidence_level: ConfidenceLevel | None = None
    observed_value: str | None = None
    expected_value: str | None = None
    evidence: list[EvidenceRef] = field(default_factory=list)
    llm_metadata: dict = field(default_factory=dict)


def confidence_from_evidence(
    segments: list[TranscriptSegment], settings: Settings
) -> ConfidenceLevel:
    """Derive evaluation confidence from the reliability of its evidence.

    A deterministic comparison is only as trustworthy as the transcription
    it read: if the words themselves are doubtful, so is the verdict.
    """
    scores = [s.asr_confidence for s in segments if s.asr_confidence is not None]
    if not scores:
        return ConfidenceLevel.HIGH
    weakest = min(scores)
    if weakest < settings.asr_confidence_floor:
        return ConfidenceLevel.LOW
    if weakest < _MEDIUM_CONFIDENCE_ASR:
        return ConfidenceLevel.MEDIUM
    return ConfidenceLevel.HIGH


def apply_low_confidence_policy(outcome: EvaluationOutcome, critical: bool) -> EvaluationOutcome:
    """Low confidence on a critical check must never stand as PASS or FAIL.

    A compliance verdict drawn from unreliable evidence is exactly the case
    a human should look at, so it is escalated rather than asserted.
    """
    if not critical or outcome.confidence_level != ConfidenceLevel.LOW:
        return outcome
    if outcome.status not in (CheckStatus.PASS, CheckStatus.FAIL):
        return outcome

    outcome.reason = (
        f"{outcome.reason} Confidence is LOW (unreliable transcription or weak interpretation) "
        f"and this check is critical, so the {outcome.status.value} verdict was downgraded to "
        "UNCERTAIN for human review."
    ).strip()
    outcome.status = CheckStatus.UNCERTAIN
    return outcome
