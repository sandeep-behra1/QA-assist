"""Seed definitions for the Energy QA checklist.

Every rule here is data -- nothing in this file is referenced by name
anywhere in the scoring engine. A new retailer's checklist is a different
set of rows, not a code change.

Two published versions exist so date-based resolution is provable:
    v1  2026-01-01 .. 2026-08-31   older disclaimer wording, no cooling-off
                                    check, looser DMO wording
    v2  2026-09-01 .. open          current wording, adds cooling-off
"""

from __future__ import annotations

from app.core.enums import BlockingBehavior, CheckType, EvaluationMethod, EvidenceSource

AGENT = EvidenceSource.AGENT_TRANSCRIPT.value
FULL = EvidenceSource.FULL_TRANSCRIPT.value

DISCLAIMER_V1 = "this call may be recorded for quality and training purposes"
DISCLAIMER_V2 = "this call may be recorded for quality and compliance purposes"


def _check(
    code: str,
    name: str,
    description: str,
    check_type: CheckType,
    method: EvaluationMethod,
    *,
    critical: bool,
    order: int,
    evidence_source: str = AGENT,
    expected_source: str | None = None,
    config: dict | None = None,
    conditions: dict | None = None,
    weight: float = 1.0,
    blocking: BlockingBehavior = BlockingBehavior.NON_BLOCKING,
) -> dict:
    return {
        "code": code,
        "name": name,
        "description": description,
        "check_type": check_type.value,
        "evaluation_method": method.value,
        "evidence_source": evidence_source,
        "expected_source": expected_source,
        "critical": critical,
        "display_order": order,
        "weight": weight,
        "blocking_behavior": blocking.value,
        "evaluation_config": config or {},
        "applicable_conditions": conditions or {},
    }


def _script_checks(disclaimer: str, dmo_phrases: list[str]) -> list[dict]:
    return [
        _check(
            "RECORDING_DISCLAIMER",
            "Recording Disclaimer",
            "Agent must state the approved call-recording disclaimer.",
            CheckType.VERBATIM,
            EvaluationMethod.NORMALIZED_TEXT,
            critical=True,
            order=10,
            config={"required_phrases": [disclaimer]},
        ),
        _check(
            "ACCOUNT_HOLDER_CONFIRMED",
            "Account Holder Confirmed",
            "Agent must confirm they are speaking to the account holder or an authorised person.",
            CheckType.VERBATIM,
            EvaluationMethod.NORMALIZED_TEXT,
            critical=True,
            order=20,
            config={
                "required_phrases": [
                    "are you the account holder",
                    "are you the authorised person",
                    "are you authorised to make changes",
                ]
            },
        ),
        _check(
            "DMO_DISCLOSURE",
            "DMO / Reference Price Disclosure",
            "Agent must disclose the offer against the Default Market Offer reference price.",
            CheckType.VERBATIM,
            EvaluationMethod.NORMALIZED_TEXT,
            critical=True,
            order=30,
            config={"required_phrases": dmo_phrases},
        ),
        _check(
            "TERMS_AND_CONDITIONS",
            "Terms & Conditions Disclosure",
            "Agent must advise that the terms and conditions will be provided.",
            CheckType.VERBATIM,
            EvaluationMethod.NORMALIZED_TEXT,
            critical=True,
            order=40,
            config={"required_phrases": ["terms and conditions"]},
        ),
    ]


def _factual_checks() -> list[dict]:
    return [
        _check(
            "EMAIL_MATCH",
            "Email Match",
            "Email confirmed on the call must match the CRM record.",
            CheckType.FACTUAL,
            EvaluationMethod.EMAIL,
            critical=True,
            order=50,
            expected_source="LEAD.customer_email",
            config={"search_keywords": ["email", "e-mail"], "context_window": 2},
        ),
        _check(
            "PEAK_RATE_MATCH",
            "Peak Usage Rate Accuracy",
            "Peak usage rate quoted must match the rate card in force on the call date.",
            CheckType.FACTUAL,
            EvaluationMethod.NUMERIC,
            critical=True,
            order=60,
            expected_source="RATE_CARD.peak_rate",
            config={
                "unit": "c/kWh",
                "tolerance": 0.01,
                "search_keywords": ["peak rate", "peak usage", "usage rate"],
            },
        ),
        _check(
            "DAILY_SUPPLY_CHARGE_MATCH",
            "Daily Supply Charge Accuracy",
            "Daily supply charge quoted must match the rate card in force on the call date.",
            CheckType.FACTUAL,
            EvaluationMethod.NUMERIC,
            critical=True,
            order=70,
            expected_source="RATE_CARD.daily_supply_charge",
            config={
                "unit": "c/day",
                "tolerance": 0.01,
                "search_keywords": ["supply charge", "daily supply"],
            },
        ),
        _check(
            "ADDRESS_MATCH",
            "Supply Address Match",
            "Supply address confirmed on the call must match the CRM record.",
            CheckType.FACTUAL,
            EvaluationMethod.NORMALIZED_TEXT,
            critical=True,
            order=80,
            expected_source="LEAD.address_line1",
            config={"search_keywords": ["address", "street", "supply address"]},
        ),
        _check(
            "DOB_MATCH",
            "Date of Birth Match",
            "Date of birth stated on the call must match the CRM record.",
            CheckType.FACTUAL,
            EvaluationMethod.DATE,
            critical=True,
            order=90,
            evidence_source=FULL,
            expected_source="LEAD.customer_dob",
            config={"search_keywords": ["date of birth", "born", "d.o.b"], "context_window": 1},
        ),
        _check(
            "NMI_MATCH",
            "NMI Match",
            "National Meter Identifier stated on the call must match the CRM record.",
            CheckType.FACTUAL,
            EvaluationMethod.IDENTIFIER,
            critical=True,
            order=100,
            evidence_source=FULL,
            expected_source="LEAD.attributes.nmi",
            config={
                "search_keywords": ["nmi", "n m i", "n-m-i", "meter identifier", "meter number"],
                "min_length": 10,
                "context_window": 1,
            },
            conditions={"LEAD.attributes.fuel_type": ["ELECTRICITY", "DUAL"]},
        ),
        _check(
            "MIRN_MATCH",
            "MIRN Match",
            "Gas meter identifier stated on the call must match the CRM record.",
            CheckType.FACTUAL,
            EvaluationMethod.IDENTIFIER,
            critical=True,
            order=110,
            evidence_source=FULL,
            expected_source="LEAD.attributes.mirn",
            config={"search_keywords": ["mirn", "gas meter"], "min_length": 10, "context_window": 1},
            conditions={"LEAD.attributes.fuel_type": ["GAS", "DUAL"]},
        ),
        _check(
            "FUEL_TYPE_MATCH",
            "Fuel Type Match",
            "Fuel type discussed must match the CRM record.",
            CheckType.FACTUAL,
            EvaluationMethod.NORMALIZED_TEXT,
            critical=True,
            order=120,
            expected_source="LEAD.attributes.fuel_type",
            config={"search_keywords": ["electricity", "gas", "fuel"]},
        ),
        _check(
            "LIFE_SUPPORT_MATCH",
            "Life Support Match",
            "Life support status confirmed on the call must match the CRM record.",
            CheckType.FACTUAL,
            EvaluationMethod.BOOLEAN,
            critical=True,
            order=130,
            evidence_source=FULL,
            expected_source="LEAD.attributes.life_support",
            config={"search_keywords": ["life support"], "context_window": 1},
        ),
        _check(
            "MOVE_IN_DATE_MATCH",
            "Move-in Date Match",
            "Move-in / connection date stated on the call must match the CRM record.",
            CheckType.FACTUAL,
            EvaluationMethod.DATE,
            critical=True,
            order=140,
            evidence_source=FULL,
            expected_source="LEAD.attributes.move_in_date",
            config={
                "search_keywords": ["move in", "moving in", "move-in", "connection date"],
                "context_window": 1,
            },
        ),
        _check(
            "CONCESSION_MATCH",
            "Concession Match",
            "Concession status confirmed on the call must match the CRM record.",
            CheckType.FACTUAL,
            EvaluationMethod.BOOLEAN,
            critical=False,
            order=150,
            evidence_source=FULL,
            expected_source="LEAD.attributes.concession",
            config={
                "search_keywords": ["concession", "pension card", "health care card"],
                "context_window": 1,
            },
        ),
        _check(
            "GIFT_CARD_VALUE_MATCH",
            "Gift Card Value Match",
            "Any gift card incentive quoted must match the approved campaign value.",
            CheckType.FACTUAL,
            EvaluationMethod.NUMERIC,
            critical=False,
            order=160,
            expected_source="LEAD.attributes.gift_card_value",
            config={"unit": "$", "tolerance": 0.01, "search_keywords": ["gift card", "voucher"]},
            conditions={"LEAD.attributes.gift_card_value": {"exists": True}},
        ),
    ]


def _behaviour_checks() -> list[dict]:
    return [
        _check(
            "DEAD_AIR",
            "Dead Air",
            "Flags silence gaps that exceed the coaching threshold.",
            CheckType.BEHAVIOUR,
            EvaluationMethod.BEHAVIOUR,
            critical=False,
            order=200,
            evidence_source=FULL,
            weight=0.5,
            config={
                "metric": "DEAD_AIR",
                "max_silence_seconds": 8.0,
                # Silence after "I'll mute the recording" is the payment-privacy sequence.
                "exclude_gaps_after_phrases": ["mute the recording", "pause the recording"],
            },
        ),
        _check(
            "INTERRUPTIONS",
            "Interruptions",
            "Flags the agent repeatedly talking over the customer.",
            CheckType.BEHAVIOUR,
            EvaluationMethod.BEHAVIOUR,
            critical=False,
            order=210,
            evidence_source=FULL,
            weight=0.5,
            config={"metric": "INTERRUPTIONS", "max_interruptions": 2, "min_overlap_seconds": 0.3},
        ),
        _check(
            "RAPPORT",
            "Rapport",
            "Interpretive coaching signal: did the agent build rapport with the customer?",
            CheckType.BEHAVIOUR,
            EvaluationMethod.BEHAVIOUR,
            critical=False,
            order=220,
            weight=0.5,
            config={
                "metric": "RAPPORT",
                # Only the opening and closing are judged, so only those are sent.
                "segment_sample": {"first": 3, "last": 3},
                "criteria": "Agent greets the customer warmly, thanks them, and offers help.",
                "semantic_keywords": [
                    "thanks for your time",
                    "happy to help",
                    "how are you",
                    "appreciate",
                ],
                "semantic_min_keywords": 2,
            },
        ),
        _check(
            "OBJECTION_HANDLING",
            "Objection Handling",
            "Interpretive coaching signal: did the agent address the customer's concerns?",
            CheckType.BEHAVIOUR,
            EvaluationMethod.BEHAVIOUR,
            critical=False,
            order=230,
            # The customer's objection is a customer turn; an agent-only view
            # cannot show whether it was addressed.
            evidence_source=FULL,
            weight=0.5,
            config={
                "metric": "OBJECTION_HANDLING",
                # Only meaningful when the customer actually raises a concern.
                "applies_when_keywords": ["not sure about", "not sure if", "not sure it", "not sure, to be honest", "stay where i am", "couldn't be bothered", "too expensive", "cheaper", "think about it", "not interested", "not much saving", "have to think", "talk to my"],
                "context_window": 2,
                "criteria": "Agent acknowledges the objection and explains without pressuring.",
                "semantic_keywords": [
                    "i understand",
                    "let me explain",
                    "no obligation",
                    "completely up to you",
                ],
                "semantic_min_keywords": 2,
            },
        ),
    ]


COOLING_OFF_CHECK = _check(
    "COOLING_OFF_DISCLOSURE",
    "Cooling-off Period Disclosure",
    "Agent must disclose the cooling-off period (added in checklist v2).",
    CheckType.VERBATIM,
    EvaluationMethod.NORMALIZED_TEXT,
    critical=True,
    order=45,
    config={"required_phrases": ["cooling off period", "cooling-off period"]},
)


PAYMENT_MUTE_CHECK = _check(
    "PAYMENT_RECORDING_MUTED",
    "Payment Details Not Recorded",
    "When payment is collected on the call, the agent must pause or mute the recording first "
    "(added in checklist v2).",
    CheckType.VERBATIM,
    EvaluationMethod.NORMALIZED_TEXT,
    critical=True,
    order=46,
    config={
        "required_phrases": [
            "mute the recording",
            "pause the recording",
            "pause recording",
            "stop the recording",
        ]
    },
    # Only applies when the CRM says payment was taken on this call.
    conditions={"LEAD.attributes.payment_collected": True},
)


def checks_v1() -> list[dict]:
    """Older wording; no cooling-off requirement yet."""
    return [
        *_script_checks(DISCLAIMER_V1, ["reference price", "default market offer"]),
        *_factual_checks(),
        *_behaviour_checks(),
    ]


def checks_v2() -> list[dict]:
    """Current wording; cooling-off added and DMO wording tightened."""
    return [
        *_script_checks(DISCLAIMER_V2, ["default market offer"]),
        COOLING_OFF_CHECK,
        PAYMENT_MUTE_CHECK,
        *_factual_checks(),
        *_behaviour_checks(),
    ]
