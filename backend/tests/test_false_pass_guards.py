"""Guards against the ways messy real speech could produce a false PASS."""

from __future__ import annotations

from datetime import date

import pytest

from app.core.config import get_settings
from app.core.enums import CheckStatus, CheckType, ConfidenceLevel, EvaluationMethod, EvidenceSource, Speaker
from app.services.llm import MockEvidenceInterpreter
from app.services.normalization import (
    contains_normalized_phrase,
    contains_phrase_ignoring_spacing,
    extract_numeric_candidates,
    redact_sensitive_data,
    words_to_digits,
)
from app.services.normalization.keywords import contains_keyword
from app.services.scoring.context import EvaluationContext
from app.services.scoring.evaluators import evaluate_behaviour, evaluate_factual, evaluate_verbatim
from tests.factories import lead_context, make_check, make_segment


def ctx(check, segments, context=None) -> EvaluationContext:
    return EvaluationContext(
        check=check,
        segments=segments,
        authoritative_context=context if context is not None else lead_context(),
        interpreter=MockEvidenceInterpreter(),
        settings=get_settings(),
        reference_date=date(2026, 9, 18),
    )


def values(text, keywords=None):
    return sorted(round(r.value, 4) for r in extract_numeric_candidates(text, keywords))


# ---- keyword boundaries ------------------------------------------------------


def test_peak_rate_keyword_does_not_match_off_peak():
    assert contains_keyword("Your peak rate is 33 cents", "peak rate")
    assert not contains_keyword("Your off-peak rate is 23 cents", "peak rate")
    assert not contains_keyword("Your off peak rate is 23 cents", "peak rate")


def test_short_keywords_do_not_match_inside_longer_words():
    assert contains_keyword("What is your NMI?", "nmi")
    assert not contains_keyword("the administration fee", "nmi")


# ---- numeric candidates ------------------------------------------------------


def test_only_numbers_carrying_a_rate_unit_are_candidates():
    text = "Your peak rate is 33.14 cents per kilowatt hour for twelve months on the Saver 5 plan."
    assert values(text, ["peak rate"]) == [33.14]


def test_the_word_for_is_never_read_as_the_digit_four():
    assert values("the rate for twelve months is thirty-three point one four cents", ["rate"]) == [33.14]


def test_percentages_are_not_rate_candidates():
    assert values("the peak rate is 33.14 cents, that is 10 per cent below the reference", ["peak rate"]) == [33.14]


def test_peak_and_off_peak_in_one_sentence_are_kept_apart():
    text = "your peak rate is 33.14 cents and your off-peak rate is 23.10 cents"
    assert values(text, ["peak rate"]) == [33.14]


def test_spoken_number_containing_and_survives_clause_splitting():
    assert values("the daily supply charge is one hundred and one point two cents", ["supply charge"]) == [101.2]


@pytest.mark.parametrize(
    "text",
    [
        "the peak rate is around thirty-three point one four cents",
        "the peak rate is between thirty-three and thirty-four cents",
        "the peak rate is 33.14 to 34 cents",
        "the peak rate is roughly 33 cents",
    ],
)
def test_approximate_or_range_figures_are_flagged_as_hedged(text):
    readings = extract_numeric_candidates(text, ["peak rate"])
    assert readings and all(r.hedged for r in readings)


def rate_check():
    return make_check(
        code="PEAK_RATE_MATCH",
        method=EvaluationMethod.NUMERIC,
        expected_source="RATE_CARD.peak_rate",
        config={"unit": "c/kWh", "tolerance": 0.01, "search_keywords": ["peak rate", "peak usage"]},
    )


@pytest.mark.parametrize(
    "text",
    [
        "Your peak rate is around thirty-three point one four cents.",
        "Your peak rate is 33.14 to 34 cents.",
        "Your peak rate is between thirty-three and thirty-four cents.",
    ],
)
def test_a_hedged_rate_is_escalated_even_when_it_contains_the_right_number(text):
    outcome = evaluate_factual(ctx(rate_check(), [make_segment(1, text)]))
    assert outcome.status == CheckStatus.UNCERTAIN
    assert "approximately or as a range" in outcome.reason


def test_a_wrong_rate_inside_a_range_can_never_pass():
    context = lead_context(peak_rate=34.0)
    outcome = evaluate_factual(ctx(rate_check(), [make_segment(1, "The peak rate is 33.14 to 34 cents.")], context))
    assert outcome.status != CheckStatus.PASS


def test_off_peak_figure_quoted_as_the_rate_does_not_pass_as_peak():
    context = lead_context(peak_rate=23.10)  # pretend the peak card equals the off-peak figure
    text = "Your off-peak rate is 23.10 cents and your peak rate is 33.14 cents."
    outcome = evaluate_factual(ctx(rate_check(), [make_segment(1, text)], context))
    assert outcome.status == CheckStatus.FAIL
    assert outcome.observed_value.startswith("33.14")


def test_same_rate_stated_twice_is_not_a_conflict():
    segments = [
        make_segment(1, "Your peak rate is thirty-three point one four cents."),
        make_segment(2, "Just to repeat, the peak rate is 33.14 cents per kilowatt hour.", start=10),
    ]
    assert evaluate_factual(ctx(rate_check(), segments)).status == CheckStatus.PASS


# ---- context window ----------------------------------------------------------


def nmi_check(window=1):
    return make_check(
        code="NMI_MATCH",
        method=EvaluationMethod.IDENTIFIER,
        evidence_source=EvidenceSource.FULL_TRANSCRIPT,
        expected_source="LEAD.attributes.nmi",
        config={"search_keywords": ["nmi"], "min_length": 10, "context_window": window},
    )


def test_an_answer_that_does_not_repeat_the_keyword_is_found_in_the_next_turn():
    segments = [
        make_segment(1, "Do you have your NMI handy?"),
        make_segment(2, "Yes, it's 6102 0012 34.", speaker=Speaker.CUSTOMER, start=4),
    ]
    assert evaluate_factual(ctx(nmi_check(), segments)).status == CheckStatus.PASS


def test_without_a_context_window_that_answer_is_not_seen():
    segments = [
        make_segment(1, "Do you have your NMI handy?"),
        make_segment(2, "Yes, it's 6102 0012 34.", speaker=Speaker.CUSTOMER, start=4),
    ]
    assert evaluate_factual(ctx(nmi_check(window=0), segments)).status == CheckStatus.UNCERTAIN


def test_a_wrong_answer_in_the_next_turn_fails_rather_than_passes():
    segments = [
        make_segment(1, "Do you have your NMI handy?"),
        make_segment(2, "Yes, it's 6102 0012 99.", speaker=Speaker.CUSTOMER, start=4),
    ]
    assert evaluate_factual(ctx(nmi_check(), segments)).status == CheckStatus.FAIL


# ---- verbatim: speech-to-text artefacts ---------------------------------------


def disclaimer_check():
    return make_check(
        code="RECORDING_DISCLAIMER",
        check_type=CheckType.VERBATIM,
        method=EvaluationMethod.NORMALIZED_TEXT,
        config={"required_phrases": ["this call may be recorded for quality and compliance purposes"]},
    )


def test_run_together_words_still_match_but_at_reduced_confidence():
    segment = make_segment(1, "Please be advised this call may be recorded for quality andcompliance purposes.")
    outcome = evaluate_verbatim(ctx(disclaimer_check(), [segment]))
    assert outcome.status == CheckStatus.PASS
    assert outcome.confidence_level == ConfidenceLevel.MEDIUM
    assert "ignoring spacing" in outcome.reason


def test_a_disclosure_split_across_adjacent_segments_matches():
    segments = [
        make_segment(1, "Please note this call may be recorded for quality", start=0, end=3),
        make_segment(2, "and compliance purposes. Now let me check the address.", start=3, end=6),
    ]
    outcome = evaluate_verbatim(ctx(disclaimer_check(), segments))
    assert outcome.status == CheckStatus.PASS
    assert [e.segment.segment_id for e in outcome.evidence] == [1, 2]


def test_a_disclosure_is_not_stitched_together_across_the_customer_speaking():
    segments = [
        make_segment(1, "Please note this call may be recorded for quality", start=0, end=3),
        make_segment(2, "Sorry, who is this?", speaker=Speaker.CUSTOMER, start=3, end=5),
        make_segment(3, "and compliance purposes.", start=5, end=7),
    ]
    assert evaluate_verbatim(ctx(disclaimer_check(), segments)).status == CheckStatus.FAIL


def test_a_missing_disclosure_still_fails_after_the_extra_passes():
    segments = [make_segment(1, "Good afternoon, how are you today?")]
    assert evaluate_verbatim(ctx(disclaimer_check(), segments)).status == CheckStatus.FAIL


def test_short_phrases_never_match_by_ignoring_spacing():
    assert not contains_phrase_ignoring_spacing("a nation", "an ation")


def test_number_words_and_digits_meet_on_both_sides():
    assert contains_normalized_phrase("I have your address as fourteen Rosella Street", "14 Rosella Street")
    assert words_to_digits("one hundred and one rosella") == "101 rosella"
    assert words_to_digits("no one for one point of contact") == "no 1 for 1 point of contact"


def test_address_is_matched_whether_heard_as_digits_or_words():
    check = make_check(
        code="ADDRESS_MATCH",
        check_type=CheckType.FACTUAL,
        method=EvaluationMethod.NORMALIZED_TEXT,
        expected_source="LEAD.address_line1",
    )
    words = evaluate_verbatim(ctx(check, [make_segment(1, "Your supply address is fourteen Rosella Street, right?")]))
    digits = evaluate_verbatim(ctx(check, [make_segment(1, "Your supply address is 14 Rosella Street, right?")]))
    other = evaluate_verbatim(ctx(check, [make_segment(1, "Your supply address is 41 Rosella Street, right?")]))
    assert words.status == digits.status == CheckStatus.PASS
    assert other.status == CheckStatus.FAIL


# ---- OTP redaction -------------------------------------------------------------


@pytest.mark.parametrize(
    "text",
    [
        "Okay, the code is 482913 and that's it.",
        "So a text message, one time code 4 8 2 9 1 3.",
        "The verification code is four eight two nine one three.",
    ],
)
def test_otp_codes_read_aloud_are_redacted(text):
    redacted = redact_sensitive_data(text)
    assert "[REDACTED]" in redacted
    assert "482913" not in redacted and "4 8 2 9 1 3" not in redacted
    assert "four eight two nine" not in redacted


def test_ordinary_numbers_near_the_word_code_are_left_alone():
    assert redact_sensitive_data("Our postcode is 2032 and the plan is 12 months.") == (
        "Our postcode is 2032 and the plan is 12 months."
    )


# ---- dead air vs the payment mute -----------------------------------------------


def dead_air_check():
    return make_check(
        code="DEAD_AIR",
        check_type=CheckType.BEHAVIOUR,
        method=EvaluationMethod.BEHAVIOUR,
        critical=False,
        evidence_source=EvidenceSource.FULL_TRANSCRIPT,
        config={
            "metric": "DEAD_AIR",
            "max_silence_seconds": 8.0,
            "exclude_gaps_after_phrases": ["mute the recording"],
        },
    )


def test_silence_after_the_agent_mutes_the_recording_is_not_dead_air():
    segments = [
        make_segment(1, "Before I take payment I need to mute the recording.", start=0, end=4),
        make_segment(2, "Okay, the recording is back on.", start=40, end=43),
    ]
    outcome = evaluate_behaviour(ctx(dead_air_check(), segments))
    assert outcome.status == CheckStatus.PASS
    assert "excused" in outcome.reason


def test_the_customer_saying_okay_before_the_mute_silence_does_not_defeat_the_exclusion():
    segments = [
        make_segment(1, "Before I take payment I need to mute the recording, okay?", start=0, end=4),
        make_segment(2, "Okay.", speaker=Speaker.CUSTOMER, start=4.5, end=5),
        make_segment(3, "The recording is back on.", start=40, end=43),
    ]
    assert evaluate_behaviour(ctx(dead_air_check(), segments)).status == CheckStatus.PASS


def test_the_exclusion_does_not_reach_far_back_into_the_call():
    segments = [
        make_segment(1, "I'll mute the recording now.", start=0, end=2),
        make_segment(2, "Okay.", speaker=Speaker.CUSTOMER, start=2.5, end=3),
        make_segment(3, "Back on.", start=12, end=13),
        make_segment(4, "Right, so about your plan.", start=13.5, end=15),
        make_segment(5, "Let me look that up.", start=15.5, end=17),
        make_segment(6, "Thanks for waiting.", start=40, end=42),
    ]
    assert evaluate_behaviour(ctx(dead_air_check(), segments)).status == CheckStatus.FAIL


def test_the_same_silence_after_ordinary_speech_is_still_dead_air():
    segments = [
        make_segment(1, "Let me just look that up for you.", start=0, end=3),
        make_segment(2, "Thanks for waiting.", start=40, end=43),
    ]
    assert evaluate_behaviour(ctx(dead_air_check(), segments)).status == CheckStatus.FAIL


# ---- payment mute check (seeded rule) --------------------------------------------


def test_payment_mute_rule_applies_only_when_payment_was_collected(seeded_db):
    from app.services.scoring.engine import score_lead

    run = score_lead(seeded_db, 3613790)
    rule = next(r for r in run.check_results if r.check_code == "PAYMENT_RECORDING_MUTED")
    assert rule.status == "NOT_APPLICABLE"
