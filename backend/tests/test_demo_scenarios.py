"""Every demo scenario reaches its documented gate through the real engine.

Uses estimated timings, so no text-to-speech is needed. The generated audio
uses real timings; the outcome depends on wording, not on exact seconds (the
two timing-based checks, dead air and interruptions, have wide margins).
"""

from __future__ import annotations

import pytest
from sqlalchemy.orm import Session

from app.demo.presets import resolve_preset
from app.demo.scenarios import SCENARIOS, SCENARIOS_BY_KEY
from app.demo.script import layout, to_segments
from app.services.ingestion.transcript import ParsedSegment, store_transcript
from app.services.leads import create_lead
from app.services.scoring.engine import score_lead


def build_sale(db: Session, scenario, lead_id: int | None = None):
    payload = resolve_preset(db, scenario.preset)
    if lead_id is not None:
        payload["lead_id"] = lead_id
    lead = create_lead(db, payload, actor="test")
    segments = [
        ParsedSegment(s["segment_id"], s["speaker"], s["start_time"], s["end_time"], s["text"], s["asr_confidence"])
        for s in to_segments(layout(scenario.items))
    ]
    store_transcript(db, lead_id=lead.id, segments=segments, actor="test")
    db.commit()
    return lead


@pytest.mark.parametrize("scenario", SCENARIOS, ids=[s.key for s in SCENARIOS])
def test_scenario_reaches_its_documented_gate(seeded_db: Session, scenario):
    lead = build_sale(seeded_db, scenario)
    run = score_lead(seeded_db, lead.id)

    by_code = {r.check_code: r.status for r in run.check_results}
    failures = {
        code: (by_code.get(code), want) for code, want in scenario.expects.items() if by_code.get(code) != want
    }
    assert run.gate_result == scenario.expected_gate, (
        f"{scenario.key}: got {run.gate_result} ({run.gate_reason}); non-passing: "
        + ", ".join(f"{r.check_code}={r.status}" for r in run.check_results if r.status not in ("PASS", "NOT_APPLICABLE"))
    )
    assert not failures, f"{scenario.key}: unexpected check statuses (got, wanted): {failures}"


def test_the_three_gate_outcomes_are_all_covered():
    assert {s.expected_gate for s in SCENARIOS} == {"APPROVED", "HOLD", "HUMAN_REVIEW"}


def test_lead_ids_are_unique_and_do_not_collide_with_the_seed():
    ids = [s.preset["lead_id"] for s in SCENARIOS]
    assert len(ids) == len(set(ids))
    seeded = {3613790, 3613827, 3613944, 3614071, 3614158, 3614203, 3614266}
    assert not seeded & set(ids)


def test_the_flagship_call_redacts_the_one_time_code(seeded_db: Session):
    from app.repositories import leads as leads_repo

    lead = build_sale(seeded_db, SCENARIOS_BY_KEY["11_flagship_messy_approve"])
    text = " ".join(s.text for s in leads_repo.latest_transcript(seeded_db, lead.id).segments)
    assert "four eight two nine one three" not in text
    assert "[REDACTED]" in text


def test_the_coaching_scenario_reports_notes_without_blocking(seeded_db: Session):
    lead = build_sale(seeded_db, SCENARIOS_BY_KEY["09_coaching_notes_approve"])
    run = score_lead(seeded_db, lead.id)
    assert run.gate_result == "APPROVED"
    assert run.summary["non_critical_fail_count"] >= 2
