"""Scoring-run immutability, overrides and audit preservation."""

from sqlalchemy.orm import Session

from app.core.enums import CheckStatus, GateDecision, OverrideReasonCode
from app.repositories import scoring as scoring_repo
from app.services.review import override_check_result
from app.services.scoring.engine import score_lead

CLEAN_SALE = 3613790
RATE_MISMATCH = 3613827
AMBIGUOUS_RATE = 3614071


def test_rescoring_creates_a_new_run_and_leaves_the_old_one_untouched(seeded_db: Session):
    first = score_lead(seeded_db, RATE_MISMATCH)
    first_id = first.id
    first_gate = first.gate_result
    first_completed = first.completed_at
    first_check_count = len(first.check_results)

    second = score_lead(seeded_db, RATE_MISMATCH)

    assert second.id != first_id

    original = scoring_repo.get_run(seeded_db, first_id)
    assert original is not None
    assert original.gate_result == first_gate
    assert original.completed_at == first_completed
    assert len(original.check_results) == first_check_count

    assert len(scoring_repo.runs_for_lead(seeded_db, RATE_MISMATCH)) == 2
    assert scoring_repo.latest_run(seeded_db, RATE_MISMATCH).id == second.id


def test_evidence_is_persisted_against_real_transcript_segments(seeded_db: Session):
    run = score_lead(seeded_db, CLEAN_SALE)
    email = next(r for r in run.check_results if r.check_code == "EMAIL_MATCH")

    assert email.evidence, "a passing factual check must cite its evidence"
    segment_ids = {s.segment_id for s in run.transcript.segments}
    for evidence in email.evidence:
        assert evidence.segment_id in segment_ids
        assert evidence.transcript_id == run.transcript_id
        assert evidence.extraction_method


def test_override_preserves_the_machine_result(seeded_db: Session):
    run = score_lead(seeded_db, AMBIGUOUS_RATE)
    assert run.gate_result == GateDecision.HUMAN_REVIEW.value

    target = next(r for r in run.check_results if r.check_code == "PEAK_RATE_MATCH")
    assert target.status == CheckStatus.UNCERTAIN.value

    result, updated_run = override_check_result(
        seeded_db,
        check_result_id=target.id,
        override_status=CheckStatus.PASS,
        reason_code=OverrideReasonCode.TRANSCRIPTION_ERROR,
        notes="Listened to the recording; the agent clearly quoted 33.14c.",
        actor="qa.lead@example.com",
    )

    # The machine's verdict is untouched...
    assert result.status == CheckStatus.UNCERTAIN.value
    # ...while the override is recorded alongside it, in full.
    override = result.latest_override
    assert override.original_status == CheckStatus.UNCERTAIN.value
    assert override.override_status == CheckStatus.PASS.value
    assert override.reason_code == OverrideReasonCode.TRANSCRIPTION_ERROR.value
    assert override.notes.startswith("Listened to the recording")
    assert override.actor == "qa.lead@example.com"
    assert override.created_at is not None

    assert result.effective_status == CheckStatus.PASS.value
    # The machine gate is preserved; the override gate is recorded separately.
    assert updated_run.gate_result == GateDecision.HUMAN_REVIEW.value
    assert updated_run.override_gate_result == GateDecision.APPROVED.value
    assert updated_run.effective_gate_result == GateDecision.APPROVED.value


def test_override_writes_an_audit_event_capturing_both_results(seeded_db: Session):
    run = score_lead(seeded_db, AMBIGUOUS_RATE)
    target = next(r for r in run.check_results if r.check_code == "PEAK_RATE_MATCH")

    override_check_result(
        seeded_db,
        check_result_id=target.id,
        override_status=CheckStatus.PASS,
        reason_code=OverrideReasonCode.EVIDENCE_MISSED,
        notes="Verified against the recording.",
        actor="qa.lead@example.com",
    )

    events = scoring_repo.list_audit_events(seeded_db, lead_id=AMBIGUOUS_RATE)
    types = [event.event_type for event in events]
    assert "CHECK_OVERRIDDEN" in types
    assert "HUMAN_REVIEW_OPENED" in types

    overridden = next(e for e in events if e.event_type == "CHECK_OVERRIDDEN")
    assert overridden.details["original_status"] == CheckStatus.UNCERTAIN.value
    assert overridden.details["override_status"] == CheckStatus.PASS.value
    assert overridden.details["reason_code"] == OverrideReasonCode.EVIDENCE_MISSED.value
    assert overridden.details["machine_gate_result"] == GateDecision.HUMAN_REVIEW.value
    assert overridden.details["gate_after_override"] == GateDecision.APPROVED.value


def test_overriding_a_pass_to_fail_can_hold_a_previously_approved_sale(seeded_db: Session):
    run = score_lead(seeded_db, CLEAN_SALE)
    assert run.gate_result == GateDecision.APPROVED.value

    target = next(r for r in run.check_results if r.check_code == "DMO_DISCLOSURE")
    _, updated = override_check_result(
        seeded_db,
        check_result_id=target.id,
        override_status=CheckStatus.FAIL,
        reason_code=OverrideReasonCode.RULE_INTERPRETATION,
        notes="Disclosure was read too fast to be meaningful.",
        actor="qa.lead@example.com",
    )
    assert updated.gate_result == GateDecision.APPROVED.value
    assert updated.effective_gate_result == GateDecision.HOLD.value


def test_scoring_records_the_full_audit_chain(seeded_db: Session):
    score_lead(seeded_db, RATE_MISMATCH)
    types = [e.event_type for e in scoring_repo.list_audit_events(seeded_db, lead_id=RATE_MISMATCH)]
    assert "SCORING_STARTED" in types
    assert "SCORING_COMPLETED" in types
    assert "SALE_HOLD" in types


def test_qa_score_is_reported_but_does_not_decide_the_gate(seeded_db: Session):
    run = score_lead(seeded_db, RATE_MISMATCH)
    # A single critical failure holds the sale even though most checks passed.
    assert run.qa_score_weighted > 90
    assert run.gate_result == GateDecision.HOLD.value
    assert run.summary["critical_fail_count"] == 1
