"""BEHAVIOUR evaluation: the shape of the call rather than its facts.

DEAD_AIR and INTERRUPTIONS are measured deterministically from segment
timings -- no model needed, and silence is derived from gaps between
utterances so the canonical transcript contract stays clean (no synthetic
"silence segments" required).

RAPPORT and OBJECTION_HANDLING are genuinely interpretive, so they are
routed to the semantic evaluator and inherit all of its controls.
"""

from __future__ import annotations

from app.core.enums import CheckStatus, ConfidenceLevel, ExecutionStatus, ExtractionMethod
from app.services.evidence import build_scope
from app.services.scoring.context import EvaluationContext, EvaluationOutcome, EvidenceRef
from app.services.scoring.evaluators.semantic import evaluate_semantic

DEAD_AIR = "DEAD_AIR"
INTERRUPTIONS = "INTERRUPTIONS"
INTERPRETIVE_METRICS = {"RAPPORT", "OBJECTION_HANDLING"}


def evaluate_behaviour(ctx: EvaluationContext) -> EvaluationOutcome:
    config = ctx.check.evaluation_config or {}
    metric = (config.get("metric") or "").upper()

    if metric in INTERPRETIVE_METRICS:
        return evaluate_semantic(ctx)
    if metric == DEAD_AIR:
        return _evaluate_dead_air(ctx, config)
    if metric == INTERRUPTIONS:
        return _evaluate_interruptions(ctx, config)

    return EvaluationOutcome(
        status=CheckStatus.UNCERTAIN,
        execution_status=ExecutionStatus.ERROR,
        confidence_level=ConfidenceLevel.LOW,
        reason=f"Check is misconfigured: unsupported behaviour metric '{metric or '(none)'}'.",
    )


def _ordered_segments(ctx: EvaluationContext):
    scope = build_scope(ctx.segments, ctx.check.evidence_source)
    return sorted(scope, key=lambda s: (s.start_time, s.segment_id))


def _evaluate_dead_air(ctx: EvaluationContext, config: dict) -> EvaluationOutcome:
    threshold = float(config.get("max_silence_seconds", 8.0))
    segments = _ordered_segments(ctx)

    if len(segments) < 2:
        return EvaluationOutcome(
            status=CheckStatus.UNCERTAIN,
            execution_status=ExecutionStatus.INCOMPLETE,
            confidence_level=ConfidenceLevel.LOW,
            reason="Fewer than two segments are available, so silence gaps cannot be measured.",
            expected_value=f"< {threshold:g}s",
        )

    gaps: list[tuple[float, object, object]] = []
    for previous, following in zip(segments, segments[1:]):
        gap = following.start_time - previous.end_time
        if gap >= threshold:
            gaps.append((gap, previous, following))

    if not gaps:
        return EvaluationOutcome(
            status=CheckStatus.PASS,
            reason=f"No silence gap reached the {threshold:g}s threshold.",
            confidence_level=ConfidenceLevel.HIGH,
            observed_value="0 gaps",
            expected_value=f"< {threshold:g}s",
        )

    longest_gap, before, after = max(gaps, key=lambda item: item[0])
    return EvaluationOutcome(
        status=CheckStatus.FAIL,
        reason=(
            f"Detected {len(gaps)} silence gap(s) at or above {threshold:g}s. The longest was "
            f"{longest_gap:.1f}s, between {before.end_time:.1f}s and {after.start_time:.1f}s."
        ),
        confidence_level=ConfidenceLevel.HIGH,
        observed_value=f"{longest_gap:.1f}s",
        expected_value=f"< {threshold:g}s",
        evidence=[
            EvidenceRef(segment=before, extraction_method=ExtractionMethod.GAP_ANALYSIS.value),
            EvidenceRef(segment=after, extraction_method=ExtractionMethod.GAP_ANALYSIS.value),
        ],
    )


def _evaluate_interruptions(ctx: EvaluationContext, config: dict) -> EvaluationOutcome:
    max_allowed = int(config.get("max_interruptions", 2))
    min_overlap = float(config.get("min_overlap_seconds", 0.3))
    segments = _ordered_segments(ctx)

    if len(segments) < 2:
        return EvaluationOutcome(
            status=CheckStatus.UNCERTAIN,
            execution_status=ExecutionStatus.INCOMPLETE,
            confidence_level=ConfidenceLevel.LOW,
            reason="Fewer than two segments are available, so interruptions cannot be measured.",
            expected_value=f"<= {max_allowed}",
        )

    overlaps = []
    for previous, following in zip(segments, segments[1:]):
        overlap = previous.end_time - following.start_time
        if overlap >= min_overlap and previous.speaker != following.speaker:
            overlaps.append((overlap, previous, following))

    observed = f"{len(overlaps)} interruption(s)"
    if len(overlaps) <= max_allowed:
        return EvaluationOutcome(
            status=CheckStatus.PASS,
            reason=f"{observed} detected, within the allowance of {max_allowed}.",
            confidence_level=ConfidenceLevel.HIGH,
            observed_value=observed,
            expected_value=f"<= {max_allowed}",
            evidence=[
                EvidenceRef(segment=item[2], extraction_method=ExtractionMethod.OVERLAP_ANALYSIS.value)
                for item in overlaps
            ],
        )

    return EvaluationOutcome(
        status=CheckStatus.FAIL,
        reason=f"{observed} detected, exceeding the allowance of {max_allowed}.",
        confidence_level=ConfidenceLevel.HIGH,
        observed_value=observed,
        expected_value=f"<= {max_allowed}",
        evidence=[
            EvidenceRef(segment=item[2], extraction_method=ExtractionMethod.OVERLAP_ANALYSIS.value)
            for item in overlaps[:5]
        ],
    )
