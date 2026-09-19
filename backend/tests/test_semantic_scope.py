"""What the model is shown, and when it is not called at all."""

from __future__ import annotations

from datetime import date

from app.core.config import get_settings
from app.core.enums import CheckStatus, CheckType, ConfidenceLevel, EvaluationMethod, EvidenceSource, Speaker
from app.services.llm.interpreter import InterpretationResult
from app.services.llm.schemas import InterpreterCall, StructuredInterpretation
from app.services.scoring.context import EvaluationContext
from app.services.scoring.evaluators import evaluate_behaviour
from tests.factories import lead_context, make_check, make_segment


class RecordingInterpreter:
    """Records exactly which segment ids it was shown; answers with a fixed interpretation."""

    def __init__(self, cite: list[int] | None = None):
        self.shown: list[list[int]] = []
        self._cite = cite

    def evaluate(self, check, transcript_segments, authoritative_context):
        ids = [s.segment_id for s in transcript_segments]
        self.shown.append(ids)
        cited = self._cite if self._cite is not None else ids[:1]
        return InterpretationResult(
            interpretation=StructuredInterpretation(
                decision="PASS", confidence_level=ConfidenceLevel.HIGH, evidence_segment_ids=cited, reason="ok"
            ),
            call=InterpreterCall(provider="rec", model="rec", prompt_version="v1",
                                 evaluation_method="BEHAVIOUR", latency_ms=1.0, succeeded=True),
        )


def ctx(check, segments, interpreter) -> EvaluationContext:
    return EvaluationContext(
        check=check, segments=segments, authoritative_context=lead_context(),
        interpreter=interpreter, settings=get_settings(), reference_date=date(2026, 9, 18),
    )


def objection_check():
    return make_check(
        code="OBJECTION_HANDLING",
        check_type=CheckType.BEHAVIOUR,
        method=EvaluationMethod.BEHAVIOUR,
        critical=False,
        evidence_source=EvidenceSource.FULL_TRANSCRIPT,
        config={
            "metric": "OBJECTION_HANDLING",
            "criteria": "Agent acknowledges the objection.",
            "applies_when_keywords": ["not sure", "stay where i am"],
            "context_window": 2,
        },
    )


def rapport_check():
    return make_check(
        code="RAPPORT",
        check_type=CheckType.BEHAVIOUR,
        method=EvaluationMethod.BEHAVIOUR,
        critical=False,
        config={"metric": "RAPPORT", "criteria": "Warm.", "segment_sample": {"first": 2, "last": 2}},
    )


def call(n: int):
    return [make_segment(i, f"Line {i}.", start=i * 5.0, end=i * 5.0 + 3) for i in range(1, n + 1)]


def test_no_objection_means_not_applicable_and_the_model_is_never_called():
    interpreter = RecordingInterpreter()
    segments = [make_segment(1, "Thanks for calling."), make_segment(2, "Sounds great.", speaker=Speaker.CUSTOMER, start=5)]
    outcome = evaluate_behaviour(ctx(objection_check(), segments, interpreter))

    assert outcome.status == CheckStatus.NOT_APPLICABLE
    assert interpreter.shown == []  # zero tokens spent


def test_only_the_objection_and_the_reply_are_sent_not_the_whole_call():
    interpreter = RecordingInterpreter()
    segments = [
        make_segment(1, "Hello, thanks for calling.", start=0, end=3),
        make_segment(2, "Great.", speaker=Speaker.CUSTOMER, start=4, end=5),
        make_segment(3, "So here is the offer.", start=6, end=9),
        make_segment(4, "I'm not sure, to be honest.", speaker=Speaker.CUSTOMER, start=10, end=12),
        make_segment(5, "I understand, no obligation.", start=13, end=16),
        make_segment(6, "Okay.", speaker=Speaker.CUSTOMER, start=17, end=18),
        make_segment(7, "Anything else?", start=19, end=21),
        make_segment(8, "No thanks. Bye.", speaker=Speaker.CUSTOMER, start=22, end=24),
    ]
    outcome = evaluate_behaviour(ctx(objection_check(), segments, interpreter))

    assert interpreter.shown == [[4, 5, 6]]
    assert outcome.status == CheckStatus.PASS
    assert [e.segment.segment_id for e in outcome.evidence] == [4]


def test_a_greeting_check_is_sent_only_the_start_and_end_of_the_call():
    interpreter = RecordingInterpreter()
    evaluate_behaviour(ctx(rapport_check(), call(10), interpreter))
    assert interpreter.shown == [[1, 2, 9, 10]]


def test_a_short_call_is_not_duplicated_by_sampling():
    interpreter = RecordingInterpreter()
    evaluate_behaviour(ctx(rapport_check(), call(3), interpreter))
    assert interpreter.shown == [[1, 2, 3]]


def test_a_citation_the_model_was_not_shown_is_discarded():
    """Segment 6 exists in the call but was never sent, so citing it is invalid."""
    interpreter = RecordingInterpreter(cite=[6])
    outcome = evaluate_behaviour(ctx(rapport_check(), call(10), interpreter))

    assert outcome.status == CheckStatus.UNCERTAIN
    assert outcome.llm_metadata["invalid_segment_ids"] == [6]
    assert outcome.evidence == []


def test_the_seeded_objection_rule_applies_only_when_a_concern_is_raised(seeded_db):
    from app.services.scoring.engine import score_lead

    # The seeded calls all contain "I'm not sure, to be honest": the rule applies.
    run = score_lead(seeded_db, 3613790)
    assert next(r for r in run.check_results if r.check_code == "OBJECTION_HANDLING").status != "NOT_APPLICABLE"
