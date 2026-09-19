"""SEMANTIC evaluation: the only path where a model's opinion is consulted.

This evaluator -- not the interpreter -- decides what the interpretation is
worth. Three controls are applied to every response, in order:

  1. every cited segment id is validated against the real transcript;
  2. a PASS that cites no valid segment is downgraded to UNCERTAIN;
  3. LOW confidence on a critical check is downgraded to UNCERTAIN.

A provider failure or malformed payload arrives here as an UNCERTAIN
interpretation and is additionally marked as a failed execution, so the gate
escalates rather than trusting a broken call.
"""

from __future__ import annotations

from app.core.enums import CheckStatus, ConfidenceLevel, ExecutionStatus, ExtractionMethod
from app.services.evidence import locate, validate_segment_ids
from app.services.scoring.context import (
    EvaluationContext,
    EvaluationOutcome,
    EvidenceRef,
    apply_low_confidence_policy,
)

_DECISION_MAP = {
    "PASS": CheckStatus.PASS,
    "FAIL": CheckStatus.FAIL,
    "UNCERTAIN": CheckStatus.UNCERTAIN,
}


def evaluate_semantic(ctx: EvaluationContext) -> EvaluationOutcome:
    check = ctx.check
    config = check.evaluation_config or {}

    located = locate(ctx.segments, check.evidence_source, config.get("search_keywords"))
    if located.scope_size == 0:
        return EvaluationOutcome(
            status=CheckStatus.UNCERTAIN,
            execution_status=ExecutionStatus.INCOMPLETE,
            confidence_level=ConfidenceLevel.LOW,
            reason="No transcript segments were available for the configured evidence source.",
        )

    shown = located.candidates

    # Some behaviours only exist when something triggers them: there is nothing
    # to judge about objection handling on a call where no objection was raised.
    # That is decided deterministically, and it also means the model is not
    # called (or sent the whole transcript) for calls where it has nothing to do.
    cues = config.get("applies_when_keywords")
    if cues:
        triggered = locate(
            ctx.segments,
            check.evidence_source,
            cues,
            context_window=int(config.get("context_window", 2)),
        )
        if not triggered.candidates:
            return EvaluationOutcome(
                status=CheckStatus.NOT_APPLICABLE,
                confidence_level=ConfidenceLevel.HIGH,
                reason=(
                    "None of this behaviour's trigger phrases appeared in the call (for example, the "
                    "customer raised no objection), so there was nothing to assess."
                ),
            )
        shown = triggered.candidates

    # Minimum necessary data: for greeting/closing behaviours only the start and
    # end of the call are sent, not the whole transcript.
    sample = config.get("segment_sample")
    if sample:
        first, last = int(sample.get("first", 0)), int(sample.get("last", 0))
        shown = shown[:first] + shown[max(len(shown) - last, first) :]

    result = ctx.interpreter.evaluate(check, shown, ctx.authoritative_context)
    interpretation = result.interpretation
    call = result.call

    llm_metadata = {
        "provider": call.provider,
        "model": call.model,
        "prompt_version": call.prompt_version,
        "evaluation_method": call.evaluation_method,
        "latency_ms": call.latency_ms,
        "succeeded": call.succeeded,
        "error": call.error,
        "claimed_decision": interpretation.decision,
        "claimed_confidence": interpretation.confidence_level.value,
        "claimed_segment_ids": list(interpretation.evidence_segment_ids),
    }

    # A citation is only valid if it points at something the model was shown.
    validation = validate_segment_ids(shown, interpretation.evidence_segment_ids)
    llm_metadata["invalid_segment_ids"] = validation.invalid_ids

    status = _DECISION_MAP.get(interpretation.decision, CheckStatus.UNCERTAIN)
    reason = interpretation.reason or "Interpreter returned no reason."

    if validation.had_invalid_references:
        reason = (
            f"{reason} Interpreter cited {len(validation.invalid_ids)} segment id(s) that do not "
            f"exist in this transcript ({validation.invalid_ids}); those citations were discarded."
        )

    # An assertion the model cannot point at is not evidence.
    if status == CheckStatus.PASS and not validation.valid_segments:
        status = CheckStatus.UNCERTAIN
        reason = (
            f"Interpreter claimed PASS but cited no valid transcript segment, so the claim could "
            f"not be verified. ({reason})"
        )

    outcome = EvaluationOutcome(
        status=status,
        reason=reason,
        execution_status=ExecutionStatus.COMPLETED if call.succeeded else ExecutionStatus.ERROR,
        confidence_level=interpretation.confidence_level,
        observed_value=interpretation.observed_value,
        expected_value=config.get("criteria") or check.description or None,
        evidence=[
            EvidenceRef(segment=segment, extraction_method=ExtractionMethod.LLM_SEMANTIC.value)
            for segment in validation.valid_segments
        ],
        llm_metadata=llm_metadata,
    )

    if not call.succeeded:
        outcome.status = CheckStatus.UNCERTAIN
        return outcome

    return apply_low_confidence_policy(outcome, check.critical)
