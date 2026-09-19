"""VERBATIM evaluation: was the required script actually said?

Absence is a genuine compliance failure here (an unread disclaimer is a
breach), so this is the one place a FAIL may be asserted from absence -- but
only after the complete relevant scope has been searched. If there is
nothing to search, the result is UNCERTAIN, not FAIL.
"""

from __future__ import annotations

from app.core.enums import CheckStatus, ConfidenceLevel, EvaluationMethod, ExecutionStatus, ExtractionMethod
from app.services.evidence import locate
from app.services.normalization import (
    contains_exact_phrase,
    contains_normalized_phrase,
    token_coverage,
)
from app.services.rules.sources import get_authoritative_value
from app.services.scoring.context import (
    EvaluationContext,
    EvaluationOutcome,
    EvidenceRef,
    apply_low_confidence_policy,
    confidence_from_evidence,
)


def evaluate_verbatim(ctx: EvaluationContext) -> EvaluationOutcome:
    check = ctx.check
    config = check.evaluation_config or {}
    phrases: list[str] = config.get("required_phrases") or (
        [config["required_phrase"]] if config.get("required_phrase") else []
    )

    # A text check may instead require that an authoritative value (an
    # address, a fuel type) was actually said aloud. Missing ground truth
    # ends the check as UNCERTAIN, exactly as it would for a factual check.
    if not phrases and check.expected_source:
        lookup = get_authoritative_value(check.expected_source, ctx.authoritative_context)
        if not lookup.found:
            return EvaluationOutcome(
                status=CheckStatus.UNCERTAIN,
                reason=(
                    f"Authoritative value '{check.expected_source}' is unavailable for this lead, "
                    "so it cannot be confirmed against the call."
                ),
                confidence_level=ConfidenceLevel.LOW,
            )
        phrases = [str(lookup.value)]

    if not phrases:
        return EvaluationOutcome(
            status=CheckStatus.UNCERTAIN,
            execution_status=ExecutionStatus.ERROR,
            confidence_level=ConfidenceLevel.LOW,
            reason="Check is misconfigured: no required phrase is defined.",
        )

    exact = check.evaluation_method == EvaluationMethod.EXACT_TEXT.value
    matcher = contains_exact_phrase if exact else contains_normalized_phrase

    located = locate(ctx.segments, check.evidence_source, config.get("search_keywords"))

    if located.scope_size == 0:
        return EvaluationOutcome(
            status=CheckStatus.UNCERTAIN,
            execution_status=ExecutionStatus.INCOMPLETE,
            confidence_level=ConfidenceLevel.LOW,
            reason=(
                "No transcript segments were available for the configured evidence source, "
                "so the absence of the required phrase could not be established."
            ),
            expected_value=phrases[0],
        )

    # Any configured phrase satisfies the check: retailers word the same
    # disclosure several approved ways.
    for segment in located.scope:
        for phrase in phrases:
            if matcher(segment.text, phrase):
                evidence = [EvidenceRef(segment=segment, extraction_method=ExtractionMethod.PHRASE_MATCH.value)]
                outcome = EvaluationOutcome(
                    status=CheckStatus.PASS,
                    reason="Required disclosure found in the agent's speech.",
                    confidence_level=confidence_from_evidence([segment], ctx.settings),
                    observed_value=segment.text,
                    expected_value=phrase,
                    evidence=evidence,
                )
                return apply_low_confidence_policy(outcome, check.critical)

    best_coverage = max(
        (token_coverage(segment.text, phrase) for segment in located.scope for phrase in phrases),
        default=0.0,
    )
    outcome = EvaluationOutcome(
        status=CheckStatus.FAIL,
        reason=(
            f"Required disclosure was not found in any of the {located.scope_size} searched "
            f"segment(s). Closest wording matched {best_coverage:.0%} of the required phrase."
        ),
        confidence_level=ConfidenceLevel.HIGH,
        observed_value=None,
        expected_value=phrases[0],
        evidence=[],
    )
    return outcome
