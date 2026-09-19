"""Evaluator behaviour: verbatim, factual, semantic and behaviour checks."""

from datetime import date

import pytest

from app.core.config import get_settings
from app.core.enums import (
    CheckStatus,
    CheckType,
    ConfidenceLevel,
    EvaluationMethod,
    EvidenceSource,
    ExecutionStatus,
    Speaker,
)
from app.services.llm import MockEvidenceInterpreter
from app.services.llm.interpreter import InterpretationResult
from app.services.llm.schemas import InterpreterCall, StructuredInterpretation
from app.services.scoring.context import EvaluationContext
from app.services.scoring.evaluators import (
    evaluate_behaviour,
    evaluate_factual,
    evaluate_semantic,
    evaluate_verbatim,
)
from tests.factories import lead_context, make_check, make_segment


def context(check, segments, ctx=None, interpreter=None) -> EvaluationContext:
    return EvaluationContext(
        check=check,
        segments=segments,
        authoritative_context=ctx if ctx is not None else lead_context(),
        interpreter=interpreter or MockEvidenceInterpreter(),
        settings=get_settings(),
        reference_date=date(2026, 9, 18),
    )


# --------------------------------------------------------------------------
# VERBATIM
# --------------------------------------------------------------------------


def disclaimer_check():
    return make_check(
        code="RECORDING_DISCLAIMER",
        check_type=CheckType.VERBATIM,
        method=EvaluationMethod.NORMALIZED_TEXT,
        config={"required_phrases": ["this call may be recorded for quality and compliance purposes"]},
    )


def test_required_disclosure_found_passes_with_evidence():
    segments = [
        make_segment(1, "Good afternoon. This call may be recorded for quality and compliance purposes."),
        make_segment(2, "How can I help?"),
    ]
    outcome = evaluate_verbatim(context(disclaimer_check(), segments))
    assert outcome.status == CheckStatus.PASS
    assert [e.segment.segment_id for e in outcome.evidence] == [1]


def test_required_disclosure_absent_fails_after_full_scope_search():
    segments = [make_segment(1, "Good afternoon, how can I help?")]
    outcome = evaluate_verbatim(context(disclaimer_check(), segments))
    assert outcome.status == CheckStatus.FAIL
    assert "searched" in outcome.reason
    assert outcome.evidence == []


def test_absence_cannot_fail_when_there_was_nothing_to_search():
    """With no in-scope segments the evaluator has not proven absence."""
    segments = [make_segment(1, "Hello?", speaker=Speaker.CUSTOMER)]
    outcome = evaluate_verbatim(context(disclaimer_check(), segments))
    assert outcome.status == CheckStatus.UNCERTAIN
    assert outcome.execution_status == ExecutionStatus.INCOMPLETE


def test_verbatim_against_authoritative_value_is_uncertain_when_source_missing():
    check = make_check(
        code="ADDRESS_MATCH",
        check_type=CheckType.FACTUAL,
        method=EvaluationMethod.NORMALIZED_TEXT,
        expected_source="LEAD.address_line1",
    )
    ctx = lead_context()
    ctx["LEAD"]["address_line1"] = None
    outcome = evaluate_verbatim(context(check, [make_segment(1, "Your address is 14 Rosella Street.")], ctx))
    assert outcome.status == CheckStatus.UNCERTAIN


# --------------------------------------------------------------------------
# FACTUAL
# --------------------------------------------------------------------------


def email_check():
    return make_check(
        code="EMAIL_MATCH",
        method=EvaluationMethod.EMAIL,
        expected_source="LEAD.customer_email",
        config={"search_keywords": ["email"]},
    )


def rate_check(**config):
    base = {"unit": "c/kWh", "tolerance": 0.01, "search_keywords": ["peak rate"]}
    base.update(config)
    return make_check(
        code="PEAK_RATE_MATCH",
        method=EvaluationMethod.NUMERIC,
        expected_source="RATE_CARD.peak_rate",
        config=base,
    )


def test_email_match_passes():
    segments = [make_segment(1, "Your email is james dot whitfield at gmail dot com?")]
    outcome = evaluate_factual(context(email_check(), segments))
    assert outcome.status == CheckStatus.PASS
    assert outcome.observed_value == "james.whitfield@gmail.com"


def test_email_mismatch_fails():
    segments = [make_segment(1, "Your email is m dot okafor at bigpond dot com?")]
    outcome = evaluate_factual(context(email_check(), segments))
    assert outcome.status == CheckStatus.FAIL
    assert outcome.observed_value == "m.okafor@bigpond.com"
    assert outcome.expected_value == "james.whitfield@gmail.com"


def test_numeric_rate_match_passes():
    segments = [make_segment(1, "Your peak rate is thirty-three point one four cents.")]
    outcome = evaluate_factual(context(rate_check(), segments))
    assert outcome.status == CheckStatus.PASS


def test_numeric_rate_mismatch_fails():
    segments = [make_segment(1, "Your peak rate is thirty-one point nine cents.")]
    outcome = evaluate_factual(context(rate_check(), segments))
    assert outcome.status == CheckStatus.FAIL
    assert outcome.expected_value.startswith("33.14")


def test_missing_authoritative_value_is_uncertain_not_fail():
    segments = [make_segment(1, "Your peak rate is thirty-three point one four cents.")]
    ctx = lead_context(include_rate_card=False)
    outcome = evaluate_factual(context(rate_check(), segments, ctx))
    assert outcome.status == CheckStatus.UNCERTAIN
    assert "unavailable" in outcome.reason


def test_value_never_stated_is_uncertain_and_never_pass():
    segments = [make_segment(1, "Thanks for your time today.")]
    outcome = evaluate_factual(context(email_check(), segments))
    assert outcome.status == CheckStatus.UNCERTAIN
    assert outcome.status is not CheckStatus.PASS


def test_contradictory_evidence_is_uncertain_without_precedence_rule():
    segments = [
        make_segment(1, "Your peak rate is thirty-one point nine cents."),
        make_segment(2, "Sorry, the peak rate is thirty-three point one four cents.", start=10),
    ]
    outcome = evaluate_factual(context(rate_check(), segments))
    assert outcome.status == CheckStatus.UNCERTAIN
    assert "Conflicting" in outcome.reason
    assert len(outcome.evidence) == 2


def test_contradictory_evidence_resolves_when_precedence_is_configured():
    segments = [
        make_segment(1, "Your peak rate is thirty-one point nine cents."),
        make_segment(2, "Sorry, the peak rate is thirty-three point one four cents.", start=10),
    ]
    outcome = evaluate_factual(context(rate_check(conflict_precedence="LAST"), segments))
    assert outcome.status == CheckStatus.PASS
    assert "precedence" in outcome.reason


def test_low_asr_confidence_downgrades_a_critical_verdict_to_uncertain():
    segments = [make_segment(1, "Your peak rate is thirty-three point one four cents.", asr=0.41)]
    outcome = evaluate_factual(context(rate_check(), segments))
    assert outcome.status == CheckStatus.UNCERTAIN
    assert outcome.confidence_level == ConfidenceLevel.LOW


def test_low_asr_confidence_does_not_escalate_a_non_critical_check():
    check = rate_check()
    check.critical = False
    segments = [make_segment(1, "Your peak rate is thirty-three point one four cents.", asr=0.41)]
    outcome = evaluate_factual(context(check, segments))
    assert outcome.status == CheckStatus.PASS
    assert outcome.confidence_level == ConfidenceLevel.LOW


def test_boolean_check_matches_crm_value():
    check = make_check(
        code="LIFE_SUPPORT",
        method=EvaluationMethod.BOOLEAN,
        evidence_source=EvidenceSource.FULL_TRANSCRIPT,
        expected_source="LEAD.attributes.life_support",
        config={"search_keywords": ["life support"]},
    )
    segments = [
        make_segment(1, "Is anyone on life support at the property?"),
        make_segment(2, "No, nobody here is on life support.", speaker=Speaker.CUSTOMER, start=5),
    ]
    outcome = evaluate_factual(context(check, segments))
    assert outcome.status == CheckStatus.PASS
    assert outcome.observed_value == "false"


def test_identifier_check_accepts_spoken_digits():
    check = make_check(
        code="NMI_MATCH",
        method=EvaluationMethod.IDENTIFIER,
        evidence_source=EvidenceSource.FULL_TRANSCRIPT,
        expected_source="LEAD.attributes.nmi",
        config={"search_keywords": ["nmi"], "min_length": 10},
    )
    segments = [
        make_segment(1, "The NMI is six one zero two zero zero one two three four.", speaker=Speaker.CUSTOMER)
    ]
    outcome = evaluate_factual(context(check, segments))
    assert outcome.status == CheckStatus.PASS


# --------------------------------------------------------------------------
# SEMANTIC (LLM boundary)
# --------------------------------------------------------------------------


def semantic_check(critical=False, **config):
    base = {"semantic_keywords": ["thanks for your time", "happy to help"], "semantic_min_keywords": 2}
    base.update(config)
    return make_check(
        code="RAPPORT",
        check_type=CheckType.BEHAVIOUR,
        method=EvaluationMethod.SEMANTIC,
        critical=critical,
        config=base,
    )


class StubInterpreter:
    """Returns a canned interpretation, for testing the evaluator's controls."""

    def __init__(self, interpretation, succeeded=True, error=None):
        self._interpretation = interpretation
        self._succeeded = succeeded
        self._error = error

    def evaluate(self, check, transcript_segments, authoritative_context):
        return InterpretationResult(
            interpretation=self._interpretation,
            call=InterpreterCall(
                provider="stub",
                model="stub",
                prompt_version="v1",
                evaluation_method=check.evaluation_method,
                latency_ms=1.0,
                succeeded=self._succeeded,
                error=self._error,
            ),
        )


def test_mock_interpreter_passes_with_cited_evidence():
    segments = [make_segment(1, "Thanks for your time today, I'm happy to help.")]
    outcome = evaluate_semantic(context(semantic_check(), segments))
    assert outcome.status == CheckStatus.PASS
    assert [e.segment.segment_id for e in outcome.evidence] == [1]
    assert outcome.llm_metadata["provider"] == "mock"


def test_semantic_check_without_matching_evidence_is_never_pass():
    segments = [make_segment(1, "Right, let's get started.")]
    outcome = evaluate_semantic(context(semantic_check(), segments))
    assert outcome.status != CheckStatus.PASS
    assert outcome.status == CheckStatus.UNCERTAIN


def test_interpreter_claiming_pass_without_citation_is_downgraded():
    interpreter = StubInterpreter(
        StructuredInterpretation(
            decision="PASS", confidence_level=ConfidenceLevel.HIGH, evidence_segment_ids=[], reason="trust me"
        )
    )
    segments = [make_segment(1, "Thanks for your time today, I'm happy to help.")]
    outcome = evaluate_semantic(context(semantic_check(), segments, interpreter=interpreter))
    assert outcome.status == CheckStatus.UNCERTAIN
    assert "cited no valid transcript segment" in outcome.reason


def test_interpreter_citing_a_nonexistent_segment_has_it_discarded():
    interpreter = StubInterpreter(
        StructuredInterpretation(
            decision="PASS",
            confidence_level=ConfidenceLevel.HIGH,
            evidence_segment_ids=[999],
            reason="cited a segment that does not exist",
        )
    )
    segments = [make_segment(1, "Thanks for your time today, I'm happy to help.")]
    outcome = evaluate_semantic(context(semantic_check(), segments, interpreter=interpreter))
    assert outcome.status == CheckStatus.UNCERTAIN
    assert outcome.llm_metadata["invalid_segment_ids"] == [999]
    assert outcome.evidence == []


def test_low_confidence_on_a_critical_semantic_check_becomes_uncertain():
    interpreter = StubInterpreter(
        StructuredInterpretation(
            decision="PASS",
            confidence_level=ConfidenceLevel.LOW,
            evidence_segment_ids=[1],
            reason="weak signal",
        )
    )
    segments = [make_segment(1, "Thanks for your time today, I'm happy to help.")]
    outcome = evaluate_semantic(context(semantic_check(critical=True), segments, interpreter=interpreter))
    assert outcome.status == CheckStatus.UNCERTAIN


def test_provider_failure_degrades_to_uncertain_and_flags_execution():
    interpreter = StubInterpreter(
        StructuredInterpretation(
            decision="UNCERTAIN", confidence_level=ConfidenceLevel.LOW, reason="connection refused"
        ),
        succeeded=False,
        error="connection refused",
    )
    segments = [make_segment(1, "Thanks for your time today.")]
    outcome = evaluate_semantic(context(semantic_check(), segments, interpreter=interpreter))
    assert outcome.status == CheckStatus.UNCERTAIN
    assert outcome.execution_status == ExecutionStatus.ERROR


@pytest.mark.parametrize("bad_decision", ["MAYBE", "approved", ""])
def test_malformed_interpreter_decision_is_rejected_by_the_schema(bad_decision):
    with pytest.raises(ValueError):
        StructuredInterpretation(
            decision=bad_decision, confidence_level=ConfidenceLevel.HIGH, reason="nonsense"
        )


def test_malformed_llm_json_becomes_uncertain_in_the_adapter():
    from app.core.config import Settings
    from app.services.llm.interpreter import OpenAICompatibleInterpreter

    # No API key configured is one of the several ways a provider call can
    # fail; every one of them must resolve to UNCERTAIN, not an exception.
    interpreter = OpenAICompatibleInterpreter(Settings(llm_provider="openai_compatible", llm_api_key=None))
    result = interpreter.evaluate(semantic_check(), [make_segment(1, "hello")], {})
    assert result.interpretation.decision == "UNCERTAIN"
    assert result.call.succeeded is False


# --------------------------------------------------------------------------
# BEHAVIOUR
# --------------------------------------------------------------------------


def test_dead_air_detected_from_gaps_between_segments():
    check = make_check(
        code="DEAD_AIR",
        check_type=CheckType.BEHAVIOUR,
        method=EvaluationMethod.BEHAVIOUR,
        critical=False,
        evidence_source=EvidenceSource.FULL_TRANSCRIPT,
        config={"metric": "DEAD_AIR", "max_silence_seconds": 8.0},
    )
    segments = [
        make_segment(1, "Let me check that for you.", start=0, end=3),
        make_segment(2, "Thanks for waiting.", start=20, end=23),
    ]
    outcome = evaluate_behaviour(context(check, segments))
    assert outcome.status == CheckStatus.FAIL
    assert outcome.observed_value == "17.0s"
    assert len(outcome.evidence) == 2


def test_no_dead_air_passes():
    check = make_check(
        code="DEAD_AIR",
        check_type=CheckType.BEHAVIOUR,
        method=EvaluationMethod.BEHAVIOUR,
        critical=False,
        evidence_source=EvidenceSource.FULL_TRANSCRIPT,
        config={"metric": "DEAD_AIR", "max_silence_seconds": 8.0},
    )
    segments = [
        make_segment(1, "Let me check that.", start=0, end=3),
        make_segment(2, "All done.", start=4, end=6),
    ]
    assert evaluate_behaviour(context(check, segments)).status == CheckStatus.PASS


def test_interruptions_counted_from_overlapping_turns():
    check = make_check(
        code="INTERRUPTIONS",
        check_type=CheckType.BEHAVIOUR,
        method=EvaluationMethod.BEHAVIOUR,
        critical=False,
        evidence_source=EvidenceSource.FULL_TRANSCRIPT,
        config={"metric": "INTERRUPTIONS", "max_interruptions": 0, "min_overlap_seconds": 0.3},
    )
    segments = [
        make_segment(1, "So the rate you'll be paying is...", start=0, end=5),
        make_segment(2, "Wait, hold on.", speaker=Speaker.CUSTOMER, start=4, end=6),
    ]
    outcome = evaluate_behaviour(context(check, segments))
    assert outcome.status == CheckStatus.FAIL
    assert outcome.observed_value == "1 interruption(s)"


def test_unsupported_behaviour_metric_errors_rather_than_passing():
    check = make_check(
        code="MYSTERY",
        check_type=CheckType.BEHAVIOUR,
        method=EvaluationMethod.BEHAVIOUR,
        critical=False,
        config={"metric": "TELEPATHY"},
    )
    outcome = evaluate_behaviour(context(check, [make_segment(1, "hello")]))
    assert outcome.status == CheckStatus.UNCERTAIN
    assert outcome.execution_status == ExecutionStatus.ERROR
