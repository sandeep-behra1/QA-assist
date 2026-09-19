"""Lightweight builders for unit tests that do not need the database."""

from __future__ import annotations

from datetime import date, datetime

from app.core.enums import (
    BlockingBehavior,
    CheckType,
    EvaluationMethod,
    EvidenceSource,
    Speaker,
)
from app.models import CheckDefinition, TranscriptSegment


def make_check(
    *,
    code: str = "TEST_CHECK",
    name: str = "Test Check",
    check_type: CheckType = CheckType.FACTUAL,
    method: EvaluationMethod = EvaluationMethod.EMAIL,
    evidence_source: EvidenceSource = EvidenceSource.AGENT_TRANSCRIPT,
    expected_source: str | None = None,
    critical: bool = True,
    config: dict | None = None,
    conditions: dict | None = None,
    blocking: BlockingBehavior = BlockingBehavior.NON_BLOCKING,
) -> CheckDefinition:
    return CheckDefinition(
        id=1,
        checklist_version_id=1,
        code=code,
        name=name,
        description="",
        check_type=check_type.value,
        evaluation_method=method.value,
        evidence_source=evidence_source.value,
        expected_source=expected_source,
        critical=critical,
        active=True,
        display_order=1,
        blocking_behavior=blocking.value,
        weight=1.0,
        evaluation_config=config or {},
        applicable_conditions=conditions or {},
    )


def make_segment(
    segment_id: int,
    text: str,
    speaker: Speaker = Speaker.AGENT,
    start: float = 0.0,
    end: float | None = None,
    asr: float | None = 0.96,
) -> TranscriptSegment:
    return TranscriptSegment(
        id=segment_id,
        transcript_id=1,
        segment_id=segment_id,
        speaker=speaker.value,
        start_time=start,
        end_time=end if end is not None else start + 3.0,
        text=text,
        asr_confidence=asr,
    )


def lead_context(
    *,
    email: str | None = "james.whitfield@gmail.com",
    peak_rate: float | None = 33.14,
    dob: date | None = date(1985, 3, 12),
    nmi: str | None = "6102001234",
    life_support: bool | None = False,
    include_rate_card: bool = True,
) -> dict:
    return {
        "LEAD": {
            "id": 3613790,
            "customer_email": email,
            "customer_dob": dob,
            "address_line1": "14 Rosella Street",
            "call_datetime": datetime(2026, 9, 18, 14, 32),
            "attributes": {
                "nmi": nmi,
                "fuel_type": "ELECTRICITY",
                "life_support": life_support,
                "move_in_date": "2026-10-01",
            },
        },
        "RETAILER": {"id": 101, "name": "Aurora Energy Retail", "code": "AURORA"},
        "PLAN": {"id": 2045, "name": "Aurora Saver Plus", "code": "SAVER", "attributes": {}},
        "RATE_CARD": (
            {
                "id": 5002,
                "peak_rate": peak_rate,
                "daily_supply_charge": 101.20,
                "unit": "c/kWh",
                "currency": "AUD",
                "attributes": {},
            }
            if include_rate_card
            else None
        ),
        "CALL": None,
    }
