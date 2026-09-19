"""Database seeding.

Seed data lives in PostgreSQL, not in Python fixtures: the running system's
source of truth is the database, and the demo must exercise the same code
path a real deployment would.
"""

from __future__ import annotations

import io
from datetime import date, datetime

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.core.enums import (
    AuditEventType,
    ChecklistVersionStatus,
    LeadStatus,
    TranscriptionStatus,
    TranscriptSource,
)
from app.models import (
    Agent,
    AuditEvent,
    Call,
    Campaign,
    CheckDefinition,
    CheckResult,
    Checklist,
    ChecklistVersion,
    Evidence,
    HumanOverride,
    HumanReview,
    Lead,
    Plan,
    RateCard,
    Retailer,
    RetailerVertical,
    ScoringRun,
    Site,
    TeamLeader,
    Transcript,
    TranscriptSegment,
    Vertical,
)
from app.seed.checks import checks_v1, checks_v2
from app.seed.demo_audio import render_call_audio
from app.seed.transcripts import CallScript, build_segments
from app.services.audit import record_event
from app.services.normalization import redact_sensitive_data
from app.services.storage import get_file_storage

VERTICALS = [
    ("ENERGY", "Energy"),
    ("BROADBAND", "Broadband"),
    ("MOBILE_INTERNET", "Mobile & Internet"),
    ("PERSONAL_LOANS", "Personal Loans"),
    ("CREDIT_CARDS", "Credit Cards"),
    ("SOLAR", "Solar"),
    ("PRIVATE_HEALTH", "Private Health"),
]

CAMPAIGNS = [("OWNED_SITE", "Owned Site"), ("PARTNER", "Partner Referral"), ("OUTBOUND", "Outbound")]
SITES = [("JAIPUR", "Jaipur"), ("MANILA", "Manila"), ("SYDNEY", "Sydney")]

# Deletion order respects foreign keys.
_DELETE_ORDER = [
    Evidence,
    HumanOverride,
    CheckResult,
    HumanReview,
    ScoringRun,
    TranscriptSegment,
    Transcript,
    Call,
    Lead,
    CheckDefinition,
    ChecklistVersion,
    Checklist,
    RateCard,
    Plan,
    RetailerVertical,
    Agent,
    TeamLeader,
    Retailer,
    Vertical,
    Campaign,
    Site,
    AuditEvent,
]


def reset_database(db: Session) -> None:
    for model in _DELETE_ORDER:
        db.execute(delete(model))
    db.commit()


# Only some sales get a recording, so the demo shows both the audio player and
# the "no recording" placeholder.
DEMO_AUDIO_LEADS = {3613790, 3613827, 3614071}


def seed_all(db: Session, *, reset: bool = False, demo_audio: bool = True) -> dict:
    if reset:
        reset_database(db)

    if db.scalar(select(Vertical).limit(1)) is not None:
        return {"status": "already_seeded"}

    verticals = _seed_verticals(db)
    campaigns_sites(db)
    retailers, plans, rate_cards = _seed_retailers(db, verticals)
    agents, team_leaders = _seed_org(db)
    checklists = _seed_checklists(db, retailers["AURORA"], verticals["ENERGY"])
    leads = _seed_leads(db, verticals, retailers, plans, agents, team_leaders, demo_audio)

    db.commit()
    _bump_sequences(db)

    return {
        "status": "seeded",
        "verticals": len(verticals),
        "retailers": len(retailers),
        "plans": len(plans),
        "rate_cards": len(rate_cards),
        "checklist_versions": len(checklists),
        "leads": len(leads),
    }


def _seed_verticals(db: Session) -> dict[str, Vertical]:
    created = {}
    for code, name in VERTICALS:
        vertical = Vertical(code=code, name=name, active=True)
        db.add(vertical)
        created[code] = vertical
    db.flush()
    return created


def campaigns_sites(db: Session) -> None:
    for code, name in CAMPAIGNS:
        db.add(Campaign(code=code, name=name))
    for code, name in SITES:
        db.add(Site(code=code, name=name))
    db.flush()


def _seed_retailers(
    db: Session, verticals: dict[str, Vertical]
) -> tuple[dict[str, Retailer], dict[str, Plan], list[RateCard]]:
    aurora = Retailer(code="AURORA", name="Aurora Energy Retail")
    meridian = Retailer(code="MERIDIAN", name="Meridian Power")
    skyline = Retailer(code="SKYLINE", name="Skyline Broadband")
    db.add_all([aurora, meridian, skyline])
    db.flush()

    for retailer, codes in (
        (aurora, ["ENERGY", "SOLAR"]),
        (meridian, ["ENERGY"]),
        (skyline, ["BROADBAND", "MOBILE_INTERNET"]),
    ):
        for code in codes:
            db.add(RetailerVertical(retailer_id=retailer.id, vertical_id=verticals[code].id))
    db.flush()

    saver = Plan(
        retailer_id=aurora.id,
        vertical_id=verticals["ENERGY"].id,
        code="AURORA_SAVER_PLUS",
        name="Aurora Saver Plus",
        description="Variable-rate residential electricity plan.",
        attributes={"contract_length_months": 12, "exit_fee": 0},
    )
    flexi = Plan(
        retailer_id=aurora.id,
        vertical_id=verticals["ENERGY"].id,
        code="AURORA_FLEXI_HOME",
        name="Aurora Flexi Home",
        description="No lock-in residential electricity plan.",
        attributes={"contract_length_months": 0, "exit_fee": 0},
    )
    meridian_plan = Plan(
        retailer_id=meridian.id,
        vertical_id=verticals["ENERGY"].id,
        code="MERIDIAN_EVERYDAY",
        name="Meridian Everyday",
        description="Rate card not yet loaded in this environment.",
        attributes={},
    )
    db.add_all([saver, flexi, meridian_plan])
    db.flush()

    rate_cards = [
        # Older card: applies to calls up to 2026-08-31.
        RateCard(
            plan_id=saver.id,
            effective_from=date(2026, 1, 1),
            effective_to=date(2026, 8, 31),
            unit="c/kWh",
            peak_rate=31.90,
            off_peak_rate=22.40,
            daily_supply_charge=98.70,
            discount_percent=8.0,
        ),
        # Current card: applies from 2026-09-01.
        RateCard(
            plan_id=saver.id,
            effective_from=date(2026, 9, 1),
            effective_to=None,
            unit="c/kWh",
            peak_rate=33.14,
            off_peak_rate=23.10,
            daily_supply_charge=101.20,
            discount_percent=10.0,
        ),
        RateCard(
            plan_id=flexi.id,
            effective_from=date(2026, 1, 1),
            effective_to=None,
            unit="c/kWh",
            peak_rate=29.85,
            off_peak_rate=21.00,
            daily_supply_charge=95.50,
            discount_percent=4.0,
        ),
    ]
    # Meridian Everyday intentionally has no rate card, so a sale on it
    # demonstrates missing authoritative data.
    db.add_all(rate_cards)
    db.flush()

    return (
        {"AURORA": aurora, "MERIDIAN": meridian, "SKYLINE": skyline},
        {"SAVER": saver, "FLEXI": flexi, "MERIDIAN_EVERYDAY": meridian_plan},
        rate_cards,
    )


def _seed_org(db: Session) -> tuple[dict[str, Agent], dict[str, TeamLeader]]:
    leaders = {
        "RAMESH": TeamLeader(name="Ramesh Iyer"),
        "ANNA": TeamLeader(name="Anna Delgado"),
    }
    db.add_all(leaders.values())
    db.flush()

    agents = {
        "PRIYA": Agent(name="Priya Nair", team_leader_id=leaders["RAMESH"].id, site="JAIPUR"),
        "DANIEL": Agent(name="Daniel Okoro", team_leader_id=leaders["RAMESH"].id, site="JAIPUR"),
        "MEI": Agent(name="Mei Tan", team_leader_id=leaders["ANNA"].id, site="MANILA"),
    }
    db.add_all(agents.values())
    db.flush()
    return agents, leaders


def _seed_checklists(db: Session, retailer: Retailer, vertical: Vertical) -> list[ChecklistVersion]:
    checklist = Checklist(
        retailer_id=retailer.id,
        vertical_id=vertical.id,
        code="AURORA_ENERGY_QA",
        name="Aurora Energy Retail - Energy QA",
    )
    db.add(checklist)
    db.flush()

    versions: list[ChecklistVersion] = []
    for number, (status, eff_from, eff_to, notes, checks) in enumerate(
        [
            (
                ChecklistVersionStatus.PUBLISHED,
                date(2026, 1, 1),
                date(2026, 8, 31),
                "Initial published checklist.",
                checks_v1(),
            ),
            (
                ChecklistVersionStatus.PUBLISHED,
                date(2026, 9, 1),
                None,
                "Updated disclaimer wording, DMO wording tightened, cooling-off check added.",
                checks_v2(),
            ),
        ],
        start=1,
    ):
        version = ChecklistVersion(
            checklist_id=checklist.id,
            version_number=number,
            status=status.value,
            effective_from=eff_from,
            effective_to=eff_to,
            notes=notes,
            published_at=datetime(2026, 1, 1) if number == 1 else datetime(2026, 8, 25),
            published_by="qa.manager@example.com",
        )
        db.add(version)
        db.flush()
        for payload in checks:
            db.add(CheckDefinition(checklist_version_id=version.id, **payload))
        db.flush()
        versions.append(version)

    record_event(
        db,
        event_type=AuditEventType.CHECKLIST_VERSION_PUBLISHED,
        entity_type="checklist_version",
        entity_id=versions[-1].id,
        actor="seed",
        details={"checklist": checklist.code, "version_number": versions[-1].version_number},
    )
    return versions


def _seed_leads(
    db: Session,
    verticals: dict[str, Vertical],
    retailers: dict[str, Retailer],
    plans: dict[str, Plan],
    agents: dict[str, Agent],
    leaders: dict[str, TeamLeader],
    demo_audio: bool = True,
) -> list[Lead]:
    energy = verticals["ENERGY"]
    aurora = retailers["AURORA"]
    saver = plans["SAVER"]

    specs = _lead_specs()
    created: list[Lead] = []

    for spec in specs:
        agent = agents[spec["agent"]]
        lead = Lead(
            id=spec["lead_id"],
            vertical_id=energy.id,
            retailer_id=aurora.id if spec["retailer"] == "AURORA" else retailers[spec["retailer"]].id,
            plan_id=(saver.id if spec["plan"] == "SAVER" else plans[spec["plan"]].id),
            agent_id=agent.id,
            team_leader_id=agent.team_leader_id,
            campaign=spec["campaign"],
            site=agent.site,
            call_datetime=spec["call_datetime"],
            customer_name=spec["customer_name"],
            customer_email=spec["customer_email"],
            customer_phone=spec["customer_phone"],
            customer_dob=spec["customer_dob"],
            address_line1=spec["address_line1"],
            suburb=spec["suburb"],
            state=spec["state"],
            postcode=spec["postcode"],
            attributes=spec["attributes"],
            status=LeadStatus.READY.value,
        )
        db.add(lead)
        db.flush()

        call = Call(
            id=spec["call_id"],
            lead_id=lead.id,
            duration_seconds=spec.get("duration_seconds", 0.0),
            transcription_status=TranscriptionStatus.NOT_STARTED.value,
        )
        db.add(call)
        db.flush()

        segments = build_segments(spec["script"])
        call.duration_seconds = round(segments[-1]["end_time"] + 1.5, 2)

        if demo_audio and lead.id in DEMO_AUDIO_LEADS:
            wav = render_call_audio(segments, call.duration_seconds)
            key = f"leads/{lead.id}/calls/{call.id}.wav"
            stored = get_file_storage().save(key, io.BytesIO(wav), "audio/wav")
            call.audio_storage_key = stored.key
            call.audio_filename = f"call_{call.id}_demo.wav"
            call.audio_content_type = "audio/wav"
            call.audio_size_bytes = stored.size_bytes

        transcript = Transcript(
            id=spec["transcript_id"],
            lead_id=lead.id,
            call_id=call.id,
            source=TranscriptSource.MANUAL_UPLOAD.value,
            language="en-AU",
            provider_metadata={"seeded": True, "scenario": spec["scenario"]},
        )
        db.add(transcript)
        db.flush()

        for segment in segments:
            db.add(
                TranscriptSegment(
                    transcript_id=transcript.id,
                    segment_id=segment["segment_id"],
                    speaker=segment["speaker"],
                    start_time=segment["start_time"],
                    end_time=segment["end_time"],
                    text=redact_sensitive_data(segment["text"]),
                    asr_confidence=segment["asr_confidence"],
                )
            )

        record_event(
            db,
            event_type=AuditEventType.LEAD_CREATED,
            entity_type="lead",
            entity_id=lead.id,
            actor="seed",
            lead_id=lead.id,
            details={"scenario": spec["scenario"]},
        )
        created.append(lead)

    db.flush()
    return created


def _base_script(**overrides) -> CallScript:
    defaults = dict(
        agent_first_name="Priya",
        retailer_name="Aurora Energy",
        disclaimer="this call may be recorded for quality and compliance purposes",
        dmo_line=(
            "Now, about the offer itself. This plan sits ten per cent below the reference price "
            "under the Default Market Offer for your area."
        ),
        customer_name="James Whitfield",
        dob_spoken="the twelfth of March nineteen eighty-five",
        address_line="14 Rosella Street, Kingsford, New South Wales, 2032",
        nmi_spoken="six one zero two zero zero one two three four",
        nmi_written="6102001234",
        move_in_spoken="the first of October",
        email_spoken="james dot whitfield at gmail dot com",
        peak_rate_spoken="thirty-three point one four cents",
        supply_charge_spoken="one hundred and one point two cents",
        include_cooling_off=True,
    )
    defaults.update(overrides)
    return CallScript(**defaults)


def _lead_specs() -> list[dict]:
    """The six demo scenarios plus a historical rule-version case."""
    common_attributes = {
        "fuel_type": "ELECTRICITY",
        "nmi": "6102001234",
        "concession": False,
        "life_support": False,
        "move_in_date": "2026-10-01",
    }

    return [
        {
            "scenario": "CLEAN_SALE",
            "lead_id": 3613790,
            "call_id": 7100452,
            "transcript_id": 900124,
            "retailer": "AURORA",
            "plan": "SAVER",
            "agent": "PRIYA",
            "campaign": "OWNED_SITE",
            "call_datetime": datetime(2026, 9, 18, 14, 32, 10),
            "customer_name": "James Whitfield",
            "customer_email": "james.whitfield@gmail.com",
            "customer_phone": "0412 555 108",
            "customer_dob": date(1985, 3, 12),
            "address_line1": "14 Rosella Street",
            "suburb": "Kingsford",
            "state": "NSW",
            "postcode": "2032",
            "attributes": dict(common_attributes),
            "script": _base_script(),
        },
        {
            "scenario": "RATE_MISMATCH",
            "lead_id": 3613827,
            "call_id": 7100489,
            "transcript_id": 900161,
            "retailer": "AURORA",
            "plan": "SAVER",
            "agent": "DANIEL",
            "campaign": "OUTBOUND",
            "call_datetime": datetime(2026, 9, 18, 15, 5, 44),
            "customer_name": "Aroha Patel",
            "customer_email": "aroha.patel@gmail.com",
            "customer_phone": "0413 555 221",
            "customer_dob": date(1979, 7, 3),
            "address_line1": "8 Marlowe Avenue",
            "suburb": "Coburg",
            "state": "VIC",
            "postcode": "3058",
            "attributes": {**common_attributes, "nmi": "6305512480"},
            "script": _base_script(
                agent_first_name="Daniel",
                customer_name="Aroha Patel",
                dob_spoken="the third of July nineteen seventy-nine",
                address_line="8 Marlowe Avenue, Coburg, Victoria, 3058",
                nmi_spoken="six three zero five five one two four eight zero",
                nmi_written="6305512480",
                email_spoken="aroha dot patel at gmail dot com",
                # Quotes last year's rate instead of the current rate card.
                peak_rate_spoken="thirty-one point nine cents",
            ),
        },
        {
            "scenario": "EMAIL_MISMATCH",
            "lead_id": 3613944,
            "call_id": 7100513,
            "transcript_id": 900188,
            "retailer": "AURORA",
            "plan": "SAVER",
            "agent": "MEI",
            "campaign": "OWNED_SITE",
            "call_datetime": datetime(2026, 9, 17, 11, 12, 5),
            "customer_name": "Michael Okafor",
            "customer_email": "m.okafor@outlook.com",
            "customer_phone": "0414 555 337",
            "customer_dob": date(1991, 11, 26),
            "address_line1": "27 Harrow Road",
            "suburb": "Stanmore",
            "state": "NSW",
            "postcode": "2048",
            "attributes": {**common_attributes, "nmi": "6209930017"},
            "script": _base_script(
                agent_first_name="Mei",
                customer_name="Michael Okafor",
                dob_spoken="the twenty-sixth of November nineteen ninety-one",
                address_line="27 Harrow Road, Stanmore, New South Wales, 2048",
                nmi_spoken="six two zero nine nine three zero zero one seven",
                nmi_written="6209930017",
                # Agent reads back the wrong provider domain.
                email_spoken="m dot okafor at bigpond dot com",
            ),
        },
        {
            "scenario": "AMBIGUOUS_RATE_LOW_ASR",
            "lead_id": 3614071,
            "call_id": 7100547,
            "transcript_id": 900214,
            "retailer": "AURORA",
            "plan": "SAVER",
            "agent": "DANIEL",
            "campaign": "PARTNER",
            "call_datetime": datetime(2026, 9, 16, 9, 48, 31),
            "customer_name": "Sofia Marchetti",
            "customer_email": "sofia.marchetti@gmail.com",
            "customer_phone": "0415 555 442",
            "customer_dob": date(1988, 1, 19),
            "address_line1": "3 Enderby Close",
            "suburb": "Parkside",
            "state": "SA",
            "postcode": "5063",
            "attributes": {**common_attributes, "nmi": "6407781290"},
            "script": _base_script(
                agent_first_name="Daniel",
                customer_name="Sofia Marchetti",
                dob_spoken="the nineteenth of January nineteen eighty-eight",
                address_line="3 Enderby Close, Parkside, South Australia, 5063",
                nmi_spoken="six four zero seven seven eight one two nine zero",
                nmi_written="6407781290",
                email_spoken="sofia dot marchetti at gmail dot com",
                # The rate was said, but the recording is too poor to rely on.
                rate_asr_confidence=0.41,
            ),
        },
        {
            "scenario": "RATE_CORRECTED_LATER",
            "lead_id": 3614158,
            "call_id": 7100588,
            "transcript_id": 900247,
            "retailer": "AURORA",
            "plan": "SAVER",
            "agent": "PRIYA",
            "campaign": "OWNED_SITE",
            "call_datetime": datetime(2026, 9, 15, 16, 22, 58),
            "customer_name": "Tomas Halvorsen",
            "customer_email": "tomas.halvorsen@gmail.com",
            "customer_phone": "0416 555 519",
            "customer_dob": date(1972, 5, 8),
            "address_line1": "91 Beaumont Terrace",
            "suburb": "New Farm",
            "state": "QLD",
            "postcode": "4005",
            "attributes": {**common_attributes, "nmi": "6511204873"},
            "script": _base_script(
                customer_name="Tomas Halvorsen",
                dob_spoken="the eighth of May nineteen seventy-two",
                address_line="91 Beaumont Terrace, New Farm, Queensland, 4005",
                nmi_spoken="six five one one two zero four eight seven three",
                nmi_written="6511204873",
                email_spoken="tomas dot halvorsen at gmail dot com",
                # Wrong rate first, corrected a moment later.
                peak_rate_spoken="thirty-one point nine cents",
                rate_correction_spoken="thirty-three point one four cents",
            ),
        },
        {
            "scenario": "DEAD_AIR",
            "lead_id": 3614203,
            "call_id": 7100612,
            "transcript_id": 900269,
            "retailer": "AURORA",
            "plan": "SAVER",
            "agent": "MEI",
            "campaign": "OUTBOUND",
            "call_datetime": datetime(2026, 9, 15, 10, 3, 17),
            "customer_name": "Grace Lombardi",
            "customer_email": "grace.lombardi@gmail.com",
            "customer_phone": "0417 555 663",
            "customer_dob": date(1995, 9, 30),
            "address_line1": "6 Waratah Lane",
            "suburb": "Fremantle",
            "state": "WA",
            "postcode": "6160",
            "attributes": {**common_attributes, "nmi": "6603345512"},
            "script": _base_script(
                agent_first_name="Mei",
                customer_name="Grace Lombardi",
                dob_spoken="the thirtieth of September nineteen ninety-five",
                address_line="6 Waratah Lane, Fremantle, Western Australia, 6160",
                nmi_spoken="six six zero three three four five five one two",
                nmi_written="6603345512",
                email_spoken="grace dot lombardi at gmail dot com",
                # Long silence while the agent looks something up.
                dead_air_before_segment=19,
                dead_air_seconds=14.5,
            ),
        },
        {
            "scenario": "HISTORICAL_RULE_VERSION",
            "lead_id": 3614266,
            "call_id": 7100655,
            "transcript_id": 900292,
            "retailer": "AURORA",
            "plan": "SAVER",
            "agent": "PRIYA",
            "campaign": "OWNED_SITE",
            # Before 2026-09-01: must resolve to checklist v1 AND the older rate card.
            "call_datetime": datetime(2026, 8, 20, 13, 41, 2),
            "customer_name": "Ellen Novak",
            "customer_email": "ellen.novak@gmail.com",
            "customer_phone": "0418 555 771",
            "customer_dob": date(1968, 2, 14),
            "address_line1": "22 Kestrel Street",
            "suburb": "Ascot Vale",
            "state": "VIC",
            "postcode": "3032",
            "attributes": {**common_attributes, "nmi": "6702218834"},
            "script": _base_script(
                customer_name="Ellen Novak",
                dob_spoken="the fourteenth of February nineteen sixty-eight",
                address_line="22 Kestrel Street, Ascot Vale, Victoria, 3032",
                nmi_spoken="six seven zero two two one eight eight three four",
                nmi_written="6702218834",
                email_spoken="ellen dot novak at gmail dot com",
                # Wording and pricing that were correct in August.
                disclaimer="this call may be recorded for quality and training purposes",
                dmo_line=(
                    "Now, about the offer. This plan sits eight per cent below the reference "
                    "price for your area."
                ),
                peak_rate_spoken="thirty-one point nine cents",
                supply_charge_spoken="ninety-eight point seven cents",
                include_cooling_off=False,
            ),
        },
    ]


def _bump_sequences(db: Session) -> None:
    """Move PostgreSQL sequences past the explicitly seeded ids.

    Seed rows use realistic hard-coded ids; without this, the next
    API-created lead would collide with one of them.
    """
    if db.bind is None or db.bind.dialect.name != "postgresql":
        return

    from sqlalchemy import text

    for sequence, model, column in (
        ("lead_id_seq", Lead, Lead.id),
        ("call_id_seq", Call, Call.id),
        ("transcript_id_seq", Transcript, Transcript.id),
    ):
        highest = db.scalar(select(column).order_by(column.desc()).limit(1))
        if highest:
            db.execute(text(f"SELECT setval('{sequence}', :value)"), {"value": int(highest)})
    db.commit()
