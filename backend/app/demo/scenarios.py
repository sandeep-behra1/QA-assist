"""Scripted synthetic Energy sales calls.

Each scenario is one call script, the sample sale details that go with it, the
gate the engine should reach, and which checks are expected to land where. The
CRM values in a preset are deliberately consistent with what is said on the
call (except where the scenario is *about* a mismatch), so typing them into the
intake form reproduces the intended outcome.

All people, addresses, numbers and emails are invented.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.demo.script import A, C, Item, Silence, Turn, spell_digits

DISCLAIMER = "this call may be recorded for quality and compliance purposes"


# ---------------------------------------------------------------------------
# Call builder
# ---------------------------------------------------------------------------


@dataclass
class CallSpec:
    agent_first: str = "Priya"
    customer_first: str = "James"
    disclaimer: bool = True
    dob_spoken: str = "the twelfth of March nineteen eighty-five"
    address_text: str = "14 Rosella Street, Kingsford"
    address_speak: str = "fourteen Rosella Street, Kingsford"
    nmi: str = "6102001234"
    life_support_answer: str = "No, nobody here is on life support."
    concession_answer: str = "No, I don't."
    move_in_spoken: str = "the first of October"
    peak_spoken: str = "thirty-three point one four cents"
    peak_prefix: str = "Your peak usage rate is"
    rate_correction_spoken: str | None = None
    supply_spoken: str = "one hundred and one point two cents"
    email_spoken: str = "james dot whitfield at gmail dot com"
    dmo: bool = True
    terms: bool = True
    cooling_off: bool = True
    objection: bool = False
    gift_card_spoken: str | None = None
    payment: str = "MUTED"  # MUTED | NOT_MUTED | NONE
    mute_seconds: float = 9.0
    otp: bool = False
    dead_air_seconds: float = 0.0
    interruptions: int = 0


def build_call(s: CallSpec) -> list[Item]:
    items: list[Item] = []
    add = items.append

    add(C(f"Hello, {s.customer_first} speaking."))
    add(A(f"Hi {s.customer_first}, good day. This is {s.agent_first} from Aurora Energy. How are you today?"))
    add(C("Good, thanks. How are you?"))

    if s.disclaimer:
        add(A(f"I'm good, thank you. Just so you know, {DISCLAIMER}. Is that okay?"))
    else:
        add(A("I'm good, thank you. We noticed you might be looking at a better electricity plan. Is that right?"))
    add(C("Yep, that's fine."))

    add(A("Before we go any further, are you the account holder for the property?"))
    add(C("Yes, I am."))

    add(A("Thank you. Can I grab your date of birth to verify the account?"))
    add(C(f"Sure, my date of birth is {s.dob_spoken}."))

    add(A(f"Perfect. I have your supply address as {s.address_text}. Is that right?",
          speak=f"Perfect. I have your supply address as {s.address_speak}. Is that right?"))
    add(C("Yes, that's the one."))
    add(A("Great. This quote is for electricity only at that address."))

    add(A("Do you have your NMI handy? It's printed on your bill.", speak="Do you have your N M I handy? It's printed on your bill."))
    add(C(f"Yes, it's {s.nmi}.", speak=f"Yes, it's {spell_digits(s.nmi)}."))

    add(A("Is anyone at the property relying on life support equipment?"))
    add(C(s.life_support_answer))
    add(A("And do you hold a concession or pension card?"))
    add(C(s.concession_answer))

    add(A("When are you moving in, or when would you like the connection to start?"))
    add(C(f"I'm moving in on {s.move_in_spoken}."))

    if s.dead_air_seconds:
        add(A("Sorry, let me just look that up for you."))
        add(Silence(s.dead_air_seconds))
        add(A("Thanks for waiting."))

    interjections = s.interruptions

    if s.dmo:
        add(A("Now, about the offer itself. This plan sits ten per cent below the reference price "
              "under the Default Market Offer for your area."))
    else:
        add(A("Now, about the offer itself. It is a competitive plan for your area."))
    if interjections > 0:
        add(C("Sorry, hang on a second.", overlap=1.1))
        interjections -= 1

    add(A(f"{s.peak_prefix} {s.peak_spoken} per kilowatt hour."))
    if s.rate_correction_spoken:
        add(A(f"Sorry, let me correct that. The peak usage rate is {s.rate_correction_spoken} per kilowatt hour."))
    if interjections > 0:
        add(C("Wait, sorry, one moment.", overlap=1.0))
        interjections -= 1

    add(A(f"And the daily supply charge is {s.supply_spoken} per day."))
    if interjections > 0:
        add(C("Hold on, can you say that again?", overlap=1.0))
        interjections -= 1
        add(A("Of course. Take your time."))

    if s.gift_card_spoken:
        add(A(f"And you'll also receive {s.gift_card_spoken} gift card when you switch."))

    if s.objection:
        add(C("I'm not sure, to be honest. I've been with my current retailer for a long time."))
        add(A("I understand, and let me explain how the discount applies. There's no obligation today, "
              "it's completely up to you."))
        add(C("Okay, that makes sense."))

    if s.cooling_off:
        add(A("You'll also have a ten business day cooling off period once you receive your welcome pack."))
    if s.terms:
        add(A("I'll email you a copy of the terms and conditions today."))

    add(A(f"Can I just confirm the best email for you? I have {s.email_spoken}."))
    add(C("Yes, that's right."))

    if s.payment == "MUTED":
        add(A("Now, to set up your direct debit I need your payment details. Before that I need to mute the "
              "recording, okay?"))
        add(C("Okay."))
        add(Silence(s.mute_seconds))
        add(A("The recording is back on. Thank you for that."))
    elif s.payment == "NOT_MUTED":
        add(A("Now, to set up your direct debit I need your payment details. Go ahead whenever you're ready."))
        add(C("Okay, it's on the way."))
        add(Silence(4.0))
        add(A("Thank you for that."))

    if s.otp:
        add(A("You'll get a text message with a code. Can you read that out to me?"))
        add(C("Sure. Okay, so the code is four eight two nine one three."))
        add(A("Mhmm. Thank you."))

    add(A("Thanks for your time today. I'm happy to help if anything comes up after the welcome pack "
          "arrives, and we appreciate your business."))
    add(C("Thanks very much. Bye."))
    return items


# ---------------------------------------------------------------------------
# Scenario + preset model
# ---------------------------------------------------------------------------


@dataclass
class Scenario:
    key: str
    title: str
    expected_gate: str
    demonstrates: str
    items: list[Item]
    preset: dict
    # check_code -> expected machine status (a few key ones; not exhaustive)
    expects: dict[str, str] = field(default_factory=dict)
    agent_voice: str = "David"
    customer_voice: str = "Zira"

    @property
    def filename(self) -> str:
        return f"{self.key}.wav"


def preset(
    *,
    lead_id: int,
    agent: str,
    campaign: str,
    call_datetime: str,
    name: str,
    email: str,
    phone: str,
    dob: str,
    address: str,
    suburb: str,
    state: str,
    postcode: str,
    nmi: str,
    move_in: str,
    life_support: bool = False,
    concession: bool = False,
    payment_collected: bool = True,
    gift_card_value: float | None = None,
) -> dict:
    attributes: dict = {
        "fuel_type": "ELECTRICITY",
        "nmi": nmi,
        "concession": concession,
        "life_support": life_support,
        "move_in_date": move_in,
        "payment_collected": payment_collected,
    }
    if gift_card_value is not None:
        attributes["gift_card_value"] = gift_card_value
    return {
        "lead_id": lead_id,
        "vertical_code": "ENERGY",
        "retailer_code": "AURORA",
        "plan_code": "AURORA_SAVER_PLUS",
        "agent_name": agent,
        "campaign": campaign,
        "call_datetime": call_datetime,
        "customer_name": name,
        "customer_email": email,
        "customer_phone": phone,
        "customer_dob": dob,
        "address_line1": address,
        "suburb": suburb,
        "state": state,
        "postcode": postcode,
        "attributes": attributes,
    }


def _person(first: str, full: str, email_local: str, address_text: str, address_speak: str, nmi: str,
            dob_spoken: str) -> dict:
    """Spoken values that must line up with the matching preset."""
    return dict(
        customer_first=first,
        dob_spoken=dob_spoken,
        address_text=address_text,
        address_speak=address_speak,
        nmi=nmi,
        email_spoken=email_local,
    )


JAMES = _person("James", "James Whitfield", "james dot whitfield at gmail dot com",
                "14 Rosella Street, Kingsford", "fourteen Rosella Street, Kingsford",
                "6102001234", "the twelfth of March nineteen eighty-five")
AROHA = _person("Aroha", "Aroha Patel", "aroha dot patel at gmail dot com",
                "8 Marlowe Avenue, Coburg", "eight Marlowe Avenue, Coburg",
                "6305512480", "the third of July nineteen seventy-nine")
MICHAEL = _person("Michael", "Michael Okafor", "m dot okafor at outlook dot com",
                  "27 Harrow Road, Stanmore", "twenty-seven Harrow Road, Stanmore",
                  "6209930017", "the twenty-sixth of November nineteen ninety-one")
SOFIA = _person("Sofia", "Sofia Marchetti", "sofia dot marchetti at gmail dot com",
                "3 Enderby Close, Parkside", "three Enderby Close, Parkside",
                "6407781290", "the nineteenth of January nineteen eighty-eight")
TOMAS = _person("Tomas", "Tomas Halvorsen", "tomas dot halvorsen at gmail dot com",
                "91 Beaumont Terrace, New Farm", "ninety-one Beaumont Terrace, New Farm",
                "6511204873", "the eighth of May nineteen seventy-two")
GRACE = _person("Grace", "Grace Lombardi", "grace dot lombardi at gmail dot com",
                "6 Waratah Lane, Fremantle", "six Waratah Lane, Fremantle",
                "6603345512", "the thirtieth of September nineteen ninety-five")
ELLEN = _person("Ellen", "Ellen Novak", "ellen dot novak at gmail dot com",
                "22 Kestrel Street, Ascot Vale", "twenty-two Kestrel Street, Ascot Vale",
                "6702218834", "the fourteenth of February nineteen sixty-eight")
DEV = _person("Dev", "Dev Malhotra", "dev dot malhotra at gmail dot com",
              "5 Coral Court, Southport", "five Coral Court, Southport",
              "6811097345", "the second of December nineteen eighty-three")
NINA = _person("Nina", "Nina Kowalski", "nina dot kowalski at gmail dot com",
               "48 Linden Way, Hawthorn", "forty-eight Linden Way, Hawthorn",
               "6905573206", "the twenty-first of August nineteen ninety")
MARCUS = _person("Marcus", "Marcus Delaney", "marcus dot delaney at gmail dot com",
                 "31 Bayview Parade, Glenelg", "thirty-one Bayview Parade, Glenelg",
                 "7003318859", "the ninth of June nineteen seventy-eight")


def _scenarios() -> list[Scenario]:
    out: list[Scenario] = []

    out.append(Scenario(
        key="01_clean_approve",
        title="Clean sale",
        expected_gate="APPROVED",
        demonstrates="Every critical check passes, including the payment-mute sequence.",
        items=build_call(CallSpec(agent_first="Priya", **JAMES)),
        preset=preset(lead_id=3614301, agent="Priya Nair", campaign="OWNED_SITE",
                      call_datetime="2026-09-18T14:32", name="James Whitfield",
                      email="james.whitfield@gmail.com", phone="0412 555 108", dob="1985-03-12",
                      address="14 Rosella Street", suburb="Kingsford", state="NSW", postcode="2032",
                      nmi="6102001234", move_in="2026-10-01"),
        expects={"RECORDING_DISCLAIMER": "PASS", "PEAK_RATE_MATCH": "PASS", "EMAIL_MATCH": "PASS",
                 "NMI_MATCH": "PASS", "PAYMENT_RECORDING_MUTED": "PASS", "DEAD_AIR": "PASS"},
    ))

    out.append(Scenario(
        key="02_wrong_rate_hold",
        title="Wrong peak rate quoted",
        expected_gate="HOLD",
        demonstrates="A critical FACTUAL mismatch: the agent quotes last year's rate (31.9c, card says 33.14c).",
        items=build_call(CallSpec(agent_first="Daniel", peak_spoken="thirty-one point nine cents", **AROHA)),
        preset=preset(lead_id=3614302, agent="Daniel Okoro", campaign="OUTBOUND",
                      call_datetime="2026-09-18T15:05", name="Aroha Patel",
                      email="aroha.patel@gmail.com", phone="0413 555 221", dob="1979-07-03",
                      address="8 Marlowe Avenue", suburb="Coburg", state="VIC", postcode="3058",
                      nmi="6305512480", move_in="2026-10-01"),
        expects={"PEAK_RATE_MATCH": "FAIL", "EMAIL_MATCH": "PASS"},
        agent_voice="David", customer_voice="Zira",
    ))

    out.append(Scenario(
        key="03_no_disclaimer_hold",
        title="Recording disclaimer never read",
        expected_gate="HOLD",
        demonstrates="A critical VERBATIM failure by absence, after the whole agent scope was searched.",
        items=build_call(CallSpec(agent_first="Mei", disclaimer=False, **MICHAEL)),
        preset=preset(lead_id=3614303, agent="Mei Tan", campaign="OWNED_SITE",
                      call_datetime="2026-09-17T11:12", name="Michael Okafor",
                      email="m.okafor@outlook.com", phone="0414 555 337", dob="1991-11-26",
                      address="27 Harrow Road", suburb="Stanmore", state="NSW", postcode="2048",
                      nmi="6209930017", move_in="2026-10-01"),
        expects={"RECORDING_DISCLAIMER": "FAIL", "PEAK_RATE_MATCH": "PASS"},
        agent_voice="Zira", customer_voice="David",
    ))

    out.append(Scenario(
        key="04_email_mismatch_hold",
        title="Email read back wrongly",
        expected_gate="HOLD",
        demonstrates="A critical FACTUAL mismatch on a spoken email (bigpond.com vs outlook.com in the CRM).",
        items=build_call(CallSpec(agent_first="Daniel", **{**MICHAEL,
                                  "email_spoken": "m dot okafor at bigpond dot com"})),
        preset=preset(lead_id=3614304, agent="Daniel Okoro", campaign="PARTNER",
                      call_datetime="2026-09-17T09:48", name="Michael Okafor",
                      email="m.okafor@outlook.com", phone="0414 555 337", dob="1991-11-26",
                      address="27 Harrow Road", suburb="Stanmore", state="NSW", postcode="2048",
                      nmi="6209930017", move_in="2026-10-01"),
        expects={"EMAIL_MATCH": "FAIL", "PEAK_RATE_MATCH": "PASS"},
    ))

    out.append(Scenario(
        key="05_rate_corrected_review",
        title="Rate quoted wrongly, then corrected",
        expected_gate="HUMAN_REVIEW",
        demonstrates="Contradictory evidence with no precedence rule: UNCERTAIN, so a person decides.",
        items=build_call(CallSpec(agent_first="Priya", peak_spoken="thirty-one point nine cents",
                                  rate_correction_spoken="thirty-three point one four cents", **SOFIA)),
        preset=preset(lead_id=3614305, agent="Priya Nair", campaign="OWNED_SITE",
                      call_datetime="2026-09-16T09:48", name="Sofia Marchetti",
                      email="sofia.marchetti@gmail.com", phone="0415 555 442", dob="1988-01-19",
                      address="3 Enderby Close", suburb="Parkside", state="SA", postcode="5063",
                      nmi="6407781290", move_in="2026-10-01"),
        expects={"PEAK_RATE_MATCH": "UNCERTAIN", "EMAIL_MATCH": "PASS"},
        agent_voice="Zira", customer_voice="David",
    ))

    out.append(Scenario(
        key="06_life_support_unclear_review",
        title="Customer unsure about life support",
        expected_gate="HUMAN_REVIEW",
        demonstrates="A hedged answer to a critical question is never guessed: UNCERTAIN.",
        items=build_call(CallSpec(agent_first="Mei",
                                  life_support_answer="Um, I think so? Maybe. I'm honestly not sure.", **TOMAS)),
        preset=preset(lead_id=3614306, agent="Mei Tan", campaign="OUTBOUND",
                      call_datetime="2026-09-15T16:22", name="Tomas Halvorsen",
                      email="tomas.halvorsen@gmail.com", phone="0416 555 519", dob="1972-05-08",
                      address="91 Beaumont Terrace", suburb="New Farm", state="QLD", postcode="4005",
                      nmi="6511204873", move_in="2026-10-01"),
        expects={"LIFE_SUPPORT_MATCH": "UNCERTAIN", "PEAK_RATE_MATCH": "PASS"},
    ))

    out.append(Scenario(
        key="07_hedged_rate_review",
        title="Rate given as 'around'",
        expected_gate="HUMAN_REVIEW",
        demonstrates="An approximate price is not verified against the rate card, even though the number is right.",
        items=build_call(CallSpec(agent_first="Daniel", peak_prefix="Your peak usage rate is around",
                                  peak_spoken="thirty-three cents", **GRACE)),
        preset=preset(lead_id=3614307, agent="Daniel Okoro", campaign="OWNED_SITE",
                      call_datetime="2026-09-15T10:03", name="Grace Lombardi",
                      email="grace.lombardi@gmail.com", phone="0417 555 663", dob="1995-09-30",
                      address="6 Waratah Lane", suburb="Fremantle", state="WA", postcode="6160",
                      nmi="6603345512", move_in="2026-10-01"),
        expects={"PEAK_RATE_MATCH": "UNCERTAIN"},
        agent_voice="Zira", customer_voice="David",
    ))

    out.append(Scenario(
        key="08_payment_not_muted_hold",
        title="Payment taken without muting the recording",
        expected_gate="HOLD",
        demonstrates="Card details would be on the recording: a critical procedural failure.",
        items=build_call(CallSpec(agent_first="Priya", payment="NOT_MUTED", **ELLEN)),
        preset=preset(lead_id=3614308, agent="Priya Nair", campaign="PARTNER",
                      call_datetime="2026-09-14T13:41", name="Ellen Novak",
                      email="ellen.novak@gmail.com", phone="0418 555 771", dob="1968-02-14",
                      address="22 Kestrel Street", suburb="Ascot Vale", state="VIC", postcode="3032",
                      nmi="6702218834", move_in="2026-10-01"),
        expects={"PAYMENT_RECORDING_MUTED": "FAIL", "PEAK_RATE_MATCH": "PASS"},
    ))

    out.append(Scenario(
        key="09_coaching_notes_approve",
        title="Dead air and interruptions (coaching notes only)",
        expected_gate="APPROVED",
        demonstrates="Non-critical behaviour failures are reported but never block a compliant sale.",
        items=build_call(CallSpec(agent_first="Mei", dead_air_seconds=14.0, interruptions=3, **DEV)),
        preset=preset(lead_id=3614309, agent="Mei Tan", campaign="OUTBOUND",
                      call_datetime="2026-09-14T10:20", name="Dev Malhotra",
                      email="dev.malhotra@gmail.com", phone="0419 555 884", dob="1983-12-02",
                      address="5 Coral Court", suburb="Southport", state="QLD", postcode="4215",
                      nmi="6811097345", move_in="2026-10-01"),
        expects={"DEAD_AIR": "FAIL", "INTERRUPTIONS": "FAIL", "PEAK_RATE_MATCH": "PASS"},
        agent_voice="Zira", customer_voice="David",
    ))

    out.append(Scenario(
        key="10_objection_handled_approve",
        title="Hesitant customer, gift card, objection handled",
        expected_gate="APPROVED",
        demonstrates="Objection handling (the LLM-assisted coaching check) plus a gift-card value match.",
        items=build_call(CallSpec(agent_first="Priya", objection=True, gift_card_spoken="a fifty dollar", **NINA)),
        preset=preset(lead_id=3614310, agent="Priya Nair", campaign="OWNED_SITE",
                      call_datetime="2026-09-13T15:10", name="Nina Kowalski",
                      email="nina.kowalski@gmail.com", phone="0420 555 145", dob="1990-08-21",
                      address="48 Linden Way", suburb="Hawthorn", state="VIC", postcode="3122",
                      nmi="6905573206", move_in="2026-10-01", gift_card_value=50.0),
        expects={"GIFT_CARD_VALUE_MATCH": "PASS", "OBJECTION_HANDLING": "PASS", "PEAK_RATE_MATCH": "PASS"},
    ))

    out.append(_flagship())
    return out


def _flagship() -> Scenario:
    """A long, messy call modelled on a real recorded sales call.

    Same shape as the reference transcript: the customer answers first, filler
    ("K?"), a hesitant customer who nearly walks, identity verification "as per
    ID", a customer who asks for things to be repeated, the recording muted for
    payment, a one-time code read aloud, and a cross-sell at the end.
    """
    items: list[Item] = [
        C("Hello. Marcus speaking."),
        A("Yes. Hi, Marcus. Good day. This is Priya from Aurora Energy comparison. How are you?"),
        C("Good. Thanks. How are you?"),
        A(f"Yeah. I'm good. Thank you. And we noticed that you're looking for a better electricity plan, "
          f"and we're calling to help you with this. By the way, please be advised that {DISCLAIMER}. K?"),
        C("Yep. That's fine."),
        A("And as I check it, your supply address is 31 Bayview Parade, Glenelg. Correct?",
          speak="And as I check it, your supply address is thirty-one Bayview Parade, Glenelg. Correct?"),
        C("Yes, that's it."),
        A("Okay. Now just to ask, Marcus, who's your current electricity provider? Do you have one?"),
        C("Redwood Energy."),
        A("You are currently with Redwood Energy. How much are you paying?"),
        C("They put it up to thirty-six cents just last month."),
        A("Okay. And are you the account holder for the property?"),
        C("Yes. It's in my name."),
        A("Okay. Because I just want to tell you, I can give you a better deal. This quote is for electricity only."),
        A("Your peak usage rate would be thirty-three point one four cents per kilowatt hour."),
        A("And the daily supply charge is one hundred and one point two cents per day. K?"),
        A("And on top of that I can also give you a free fifty dollar gift card, at no extra cost."),
        C("Who is that through?"),
        A("That is from Aurora Energy. It's a hundred percent free. K?"),
        C("Right. Maybe I'll just stay where I am. I couldn't be bothered, because it's not much savings."),
        A("I really understand, and let me explain. There's no obligation, it's completely up to you. "
          "There's also no exit fee, so you can leave whenever you like. K?"),
        C("Okay. So how does it work? How does it get changed over?"),
        A("We can quickly set this up for you without paying any fee. K? Now I just want to tell you that "
          "this plan sits ten per cent below the reference price under the Default Market Offer for your area. "
          "And you'll also have a ten business day cooling off period once you receive your welcome pack. K?"),
        C("Okay. Sounds like a good deal."),
        A("Yeah. That's why we can quickly set it up for you. I'll email you a copy of the terms and "
          "conditions today. K?"),
        A("Can you please verify your first and last name as per ID, please?"),
        C("Sorry. I didn't get that."),
        A("Can you please verify your first and last name as per ID?"),
        C("Marcus Delaney."),
        A("Okay. And then your email address, can you please also verify it? I have "
          "marcus dot delaney at gmail dot com. Thank you."),
        C("Yes, that's right."),
        A("And your mobile number, can you please also verify it?"),
        C("Zero four two one, five five five, three three one."),
        A("Okay. And your date of birth?"),
        C("The ninth of June nineteen seventy-eight."),
        A("Okay. And do you have your NMI handy? It's printed on your bill.",
          speak="Okay. And do you have your N M I handy? It's printed on your bill."),
        C("Just a sec. Yep. It's 7003318859.", speak=f"Just a sec. Yep. It's {spell_digits('7003318859')}."),
        A("Thank you. Is anyone at the property relying on life support equipment?"),
        C("No. Nobody here is on life support."),
        A("And do you hold a concession or pension card?"),
        C("No, I don't."),
        A("And when are you moving in, or when would you like the connection to start?"),
        C("As soon as possible. Actually I'm moving in on the first of October."),
        A("Okay. Now, to set up your account, Marcus, we need to collect your preferred payment method. "
          "But before that, I need to mute the recording. K?"),
        C("Okay."),
        Silence(12.0),
        A("Okay. The recording is already resumed. Now, do you have access to your email right now?"),
        C("Yes. I do."),
        A("Okay. You'll get a text message with a code. Can you please read that out?"),
        C("Okay. So a text message. The code is four eight two nine one three."),
        A("Mhmm. And then click submit application. Just let me know if you already have the reference number."),
        C("Yep. It's E N one two nine four seven."),
        A("Thank you for that. That means that you already took advantage of the offer. Okay? "
          "Congratulations for choosing Aurora Energy. And now since we already helped with your electricity, "
          "how about your gas or internet? Maybe we could also give you a quote for that."),
        C("No, I don't have gas, and my internet is fine."),
        A("I see. Okay. If that's the case, thanks for your time today, Marcus. I'm happy to help if anything "
          "comes up after the welcome pack arrives, and we appreciate your business. Cheers, and have a wonderful day."),
        C("Okay. Thank you."),
        A("You're welcome. Bye for now."),
    ]
    return Scenario(
        key="11_flagship_messy_approve",
        title="Long messy call modelled on a real recording",
        expected_gate="APPROVED",
        demonstrates=("Filler and repetition, a hesitant customer, ID verification, a mute for payment, "
                      "a one-time code read aloud (redacted), a gift card and a cross-sell."),
        items=items,
        preset=preset(lead_id=3614311, agent="Priya Nair", campaign="OUTBOUND",
                      call_datetime="2026-09-12T11:05", name="Marcus Delaney",
                      email="marcus.delaney@gmail.com", phone="0421 555 331", dob="1978-06-09",
                      address="31 Bayview Parade", suburb="Glenelg", state="SA", postcode="5045",
                      nmi="7003318859", move_in="2026-10-01", gift_card_value=50.0),
        expects={"GIFT_CARD_VALUE_MATCH": "PASS", "PAYMENT_RECORDING_MUTED": "PASS",
                 "PEAK_RATE_MATCH": "PASS", "DEAD_AIR": "PASS"},
    )


SCENARIOS: list[Scenario] = _scenarios()
SCENARIOS_BY_KEY = {s.key: s for s in SCENARIOS}


def turns_of(scenario: Scenario) -> list[Turn]:
    return [i for i in scenario.items if isinstance(i, Turn)]
