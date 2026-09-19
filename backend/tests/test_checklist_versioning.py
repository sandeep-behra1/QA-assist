"""Checklist versioning: date-based resolution, immutability, and extensibility."""

from datetime import date, datetime

import pytest
from sqlalchemy.orm import Session

from app.core.enums import (
    ChecklistVersionStatus,
    CheckType,
    EvaluationMethod,
    EvidenceSource,
    LeadStatus,
)
from app.models import Checklist, ChecklistVersion, Lead, Retailer, RetailerVertical, Vertical
from app.repositories import checklists as checklist_repo
from app.services.ingestion import store_transcript
from app.services.ingestion.transcript import ParsedSegment
from app.services.rules.authoring import (
    ChecklistImmutableError,
    add_check,
    create_draft_version,
    publish_version,
    update_check,
)
from app.services.rules.resolver import resolve_checklist_version
from app.services.scoring.engine import score_lead


def _versions(db: Session) -> list[ChecklistVersion]:
    checklist = checklist_repo.list_checklists(db)[0]
    return checklist_repo.versions_for_retailer_vertical(
        db, checklist.retailer_id, checklist.vertical_id
    )


def test_call_date_selects_the_version_in_force_at_the_time(seeded_db: Session):
    versions = _versions(seeded_db)

    august = resolve_checklist_version(versions, date(2026, 8, 20))
    september = resolve_checklist_version(versions, date(2026, 9, 15))

    assert august.version_number == 1
    assert september.version_number == 2


def test_version_boundaries_are_inclusive(seeded_db: Session):
    versions = _versions(seeded_db)
    assert resolve_checklist_version(versions, date(2026, 8, 31)).version_number == 1
    assert resolve_checklist_version(versions, date(2026, 9, 1)).version_number == 2


def test_no_version_covers_a_date_before_the_first_one(seeded_db: Session):
    assert resolve_checklist_version(_versions(seeded_db), date(2025, 6, 1)) is None


def test_draft_versions_are_never_used_for_scoring(seeded_db: Session):
    checklist = checklist_repo.list_checklists(seeded_db)[0]
    draft = create_draft_version(
        seeded_db, checklist_id=checklist.id, copy_from_version_id=None, notes="wip"
    )
    draft.effective_from = date(2026, 1, 1)
    seeded_db.commit()

    resolved = resolve_checklist_version(_versions(seeded_db), date(2026, 9, 15))
    assert resolved.id != draft.id
    assert resolved.status == ChecklistVersionStatus.PUBLISHED.value


def test_a_historical_call_is_scored_against_the_older_rules_and_rate_card(seeded_db: Session):
    """The August sale quotes August's rate and August's disclaimer wording.

    Under the current (v2) rules both would be wrong, so this only passes if
    version resolution actually happened.
    """
    run = score_lead(seeded_db, 3614266)

    assert run.checklist_version.version_number == 1
    assert run.gate_result == "APPROVED"

    rate = next(r for r in run.check_results if r.check_code == "PEAK_RATE_MATCH")
    assert rate.expected_value.startswith("31.9")
    assert rate.status == "PASS"

    # v2 added the cooling-off check; it must not appear on a v1 run.
    assert not any(r.check_code == "COOLING_OFF_DISCLOSURE" for r in run.check_results)


def test_current_call_uses_current_rules_and_rate_card(seeded_db: Session):
    run = score_lead(seeded_db, 3613790)
    assert run.checklist_version.version_number == 2
    rate = next(r for r in run.check_results if r.check_code == "PEAK_RATE_MATCH")
    assert rate.expected_value.startswith("33.14")
    assert any(r.check_code == "COOLING_OFF_DISCLOSURE" for r in run.check_results)


def test_published_version_cannot_gain_a_check(seeded_db: Session):
    published = [v for v in _versions(seeded_db) if v.is_published][-1]
    with pytest.raises(ChecklistImmutableError):
        add_check(
            seeded_db,
            version_id=published.id,
            payload={
                "code": "SNEAKY",
                "name": "Sneaky",
                "description": "",
                "check_type": CheckType.VERBATIM.value,
                "evaluation_method": EvaluationMethod.NORMALIZED_TEXT.value,
                "evidence_source": EvidenceSource.AGENT_TRANSCRIPT.value,
                "critical": True,
                "evaluation_config": {"required_phrases": ["anything"]},
            },
        )


def test_published_check_cannot_be_edited(seeded_db: Session):
    published = [v for v in _versions(seeded_db) if v.is_published][-1]
    check = published.checks[0]
    with pytest.raises(ChecklistImmutableError):
        update_check(seeded_db, check_id=check.id, payload={"critical": False})


def test_publishing_a_draft_closes_the_previous_version_window(seeded_db: Session):
    checklist = checklist_repo.list_checklists(seeded_db)[0]
    previous = [v for v in checklist.versions if v.is_published][-1]
    assert previous.effective_to is None

    draft = create_draft_version(
        seeded_db, checklist_id=checklist.id, copy_from_version_id=previous.id, notes="v3"
    )
    assert len(draft.checks) == len(previous.checks)

    published = publish_version(seeded_db, version_id=draft.id, effective_from=date(2026, 10, 1))
    seeded_db.refresh(previous)

    assert published.status == ChecklistVersionStatus.PUBLISHED.value
    assert previous.effective_to == date(2026, 9, 30)

    versions = _versions(seeded_db)
    assert resolve_checklist_version(versions, date(2026, 9, 30)).version_number == previous.version_number
    assert resolve_checklist_version(versions, date(2026, 10, 1)).version_number == published.version_number


def test_a_new_retailer_can_be_onboarded_without_code_changes(db: Session):
    """A whole new retailer, checklist and scored sale, using only data."""
    vertical = Vertical(code="ENERGY", name="Energy")
    db.add(vertical)
    db.flush()

    retailer = Retailer(code="NEWCO", name="Newco Energy")
    db.add(retailer)
    db.flush()
    db.add(RetailerVertical(retailer_id=retailer.id, vertical_id=vertical.id))

    checklist = Checklist(
        retailer_id=retailer.id, vertical_id=vertical.id, code="NEWCO_QA", name="Newco QA"
    )
    db.add(checklist)
    db.commit()

    draft = create_draft_version(db, checklist_id=checklist.id, notes="initial")
    add_check(
        db,
        version_id=draft.id,
        payload={
            "code": "NEWCO_GREETING",
            "name": "Approved Greeting",
            "description": "Agent must use the approved greeting.",
            "check_type": CheckType.VERBATIM.value,
            "evaluation_method": EvaluationMethod.NORMALIZED_TEXT.value,
            "evidence_source": EvidenceSource.AGENT_TRANSCRIPT.value,
            "critical": True,
            "display_order": 10,
            "evaluation_config": {"required_phrases": ["welcome to newco energy"]},
        },
    )
    publish_version(db, version_id=draft.id, effective_from=date(2026, 1, 1))

    lead = Lead(
        vertical_id=vertical.id,
        retailer_id=retailer.id,
        call_datetime=datetime(2026, 9, 18, 10, 0),
        customer_name="Test Customer",
        status=LeadStatus.READY.value,
    )
    db.add(lead)
    db.commit()

    store_transcript(
        db,
        lead_id=lead.id,
        segments=[
            ParsedSegment(1, "AGENT", 0.0, 3.0, "Welcome to Newco Energy, how can I help?", 0.97)
        ],
    )
    db.commit()

    run = score_lead(db, lead.id)
    assert run.gate_result == "APPROVED"
    assert run.check_results[0].check_code == "NEWCO_GREETING"
