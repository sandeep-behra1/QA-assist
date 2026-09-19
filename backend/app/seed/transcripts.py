"""Synthetic Energy sales-call transcripts for the demo.

One realistic call script is parameterised so each scenario differs only in
the thing it is meant to demonstrate -- a wrong rate, a mistyped email, a
noisy recording -- which keeps the demo honest: nothing else is nudged to
make an outcome come out the way the README claims.

All customer details are fictional.
"""

from __future__ import annotations

from dataclasses import dataclass, field

DEFAULT_ASR = 0.96


@dataclass
class CallScript:
    agent_first_name: str
    retailer_name: str
    disclaimer: str
    dmo_line: str
    customer_name: str
    dob_spoken: str
    address_line: str
    nmi_spoken: str
    nmi_written: str
    move_in_spoken: str
    email_spoken: str
    peak_rate_spoken: str
    supply_charge_spoken: str
    include_cooling_off: bool = True
    concession_answer: str = "No, I don't have a concession card."
    life_support_answer: str = "No, nobody here is on life support."
    rate_asr_confidence: float = DEFAULT_ASR
    rate_correction_spoken: str | None = None
    dead_air_before_segment: int | None = None
    dead_air_seconds: float = 0.0
    gift_card_line: str | None = None
    extra_asr_overrides: dict[int, float] = field(default_factory=dict)


def build_segments(script: CallScript) -> list[dict]:
    """Render a CallScript into canonical transcript segments."""
    lines: list[tuple[str, str, float]] = [
        (
            "AGENT",
            f"Good afternoon, you're speaking with {script.agent_first_name} from "
            f"{script.retailer_name}. How are you today? Just so you know, {script.disclaimer}.",
            7.2,
        ),
        ("CUSTOMER", "Yeah, good thanks. That's fine, go ahead.", 2.4),
        ("AGENT", "Before we go any further, are you the account holder for the property?", 3.6),
        ("CUSTOMER", "Yes, I am.", 1.4),
        ("AGENT", "Thank you. Can I grab your date of birth just to verify the account?", 3.8),
        ("CUSTOMER", f"Sure, my date of birth is {script.dob_spoken}.", 3.6),
        (
            "AGENT",
            f"Perfect, that matches our records. I also have your supply address as "
            f"{script.address_line}. Is that right?",
            6.0,
        ),
        ("CUSTOMER", "Yes, that's the one.", 1.6),
        ("AGENT", "Great. This quote is for electricity only at that address.", 3.4),
        ("AGENT", "Do you have your NMI handy? It's the meter identifier printed on your bill.", 4.4),
        ("CUSTOMER", f"Yes, the NMI is {script.nmi_spoken}.", 6.5),
        ("AGENT", f"Thank you, so that's {script.nmi_written}.", 3.2),
        ("AGENT", "Is anyone at the property relying on life support equipment?", 3.6),
        ("CUSTOMER", script.life_support_answer, 2.6),
        ("AGENT", "And do you hold a concession or pension card?", 2.8),
        ("CUSTOMER", script.concession_answer, 2.6),
        ("AGENT", "When are you moving in, or when would you like the connection to start?", 4.2),
        ("CUSTOMER", f"I'm moving in on {script.move_in_spoken}.", 3.0),
        ("AGENT", script.dmo_line, 6.4),
        (
            "AGENT",
            f"Your peak usage rate is {script.peak_rate_spoken} per kilowatt hour.",
            4.6,
        ),
    ]

    if script.rate_correction_spoken:
        lines.append(
            (
                "AGENT",
                f"Sorry, let me correct that. The peak usage rate is "
                f"{script.rate_correction_spoken} per kilowatt hour.",
                5.2,
            )
        )

    lines += [
        (
            "AGENT",
            f"And the daily supply charge is {script.supply_charge_spoken} per day.",
            4.2,
        ),
    ]

    if script.gift_card_line:
        lines.append(("AGENT", script.gift_card_line, 4.0))

    lines += [
        (
            "CUSTOMER",
            "I'm not sure, to be honest. I've been with my current retailer for a long time.",
            4.4,
        ),
        (
            "AGENT",
            "I understand, and let me explain how the discount applies. There's no obligation "
            "today, it's completely up to you.",
            6.8,
        ),
        ("CUSTOMER", "Okay, that makes sense.", 1.8),
    ]

    if script.include_cooling_off:
        lines.append(
            (
                "AGENT",
                "You'll also have a ten business day cooling off period once you receive your "
                "welcome pack.",
                5.4,
            )
        )

    lines += [
        ("AGENT", "I'll email you a copy of the terms and conditions today.", 3.6),
        (
            "AGENT",
            f"Can I just confirm the best email for you? I have {script.email_spoken}.",
            6.2,
        ),
        ("CUSTOMER", "Yes, that's right.", 1.6),
        (
            "AGENT",
            "Thanks for your time today. I'm happy to help if anything comes up after the "
            "welcome pack arrives.",
            5.6,
        ),
        ("CUSTOMER", "Thanks very much. Bye.", 1.8),
    ]

    return _with_timings(lines, script)


def _with_timings(lines: list[tuple[str, str, float]], script: CallScript) -> list[dict]:
    segments: list[dict] = []
    cursor = 3.5  # a little lead-in before the agent speaks
    natural_gap = 0.45

    for index, (speaker, text, duration) in enumerate(lines, start=1):
        if script.dead_air_before_segment == index:
            cursor += script.dead_air_seconds

        start = round(cursor, 2)
        end = round(start + duration, 2)
        confidence = script.extra_asr_overrides.get(index, DEFAULT_ASR)
        # The rate quote is the segment scenarios most often degrade.
        if "peak usage rate is" in text:
            confidence = script.rate_asr_confidence

        segments.append(
            {
                "segment_id": index,
                "speaker": speaker,
                "start_time": start,
                "end_time": end,
                "text": text,
                "asr_confidence": round(confidence, 2),
            }
        )
        cursor = end + natural_gap

    return segments


def canonical_transcript(lead_id: int, call_id: int, segments: list[dict], transcript_id: int) -> dict:
    """Wrap segments in the canonical transcript envelope."""
    return {
        "transcript_id": transcript_id,
        "lead_id": lead_id,
        "call_id": call_id,
        "source": "MANUAL_UPLOAD",
        "language": "en-AU",
        "segments": segments,
    }
