"""Normalisation: spoken forms must reach the same canonical value as written ones."""

from datetime import date

import pytest

from app.services.normalization import (
    compare_identifiers,
    extract_boolean,
    extract_date,
    extract_email,
    extract_identifier,
    extract_numeric,
    normalize_email,
    normalize_identifier,
    normalize_phone,
    redact_sensitive_data,
)
from app.services.normalization.numeric import NumericReading, convert_to_unit


@pytest.mark.parametrize(
    "text,expected",
    [
        ("Can I confirm your email is john dot smith at gmail dot com?", "john.smith@gmail.com"),
        ("your email is john dot smith at g mail dot com, correct?", "john.smith@gmail.com"),
        ("I have j.smith@gmail.com on file.", "j.smith@gmail.com"),
        ("that's m dot okafor at bigpond dot com", "m.okafor@bigpond.com"),
        ("email is sarah underscore lee at hot mail dot com", "sarah_lee@hotmail.com"),
    ],
)
def test_spoken_and_written_emails_normalize_to_canonical_form(text, expected):
    assert extract_email(text) == expected


def test_email_absent_returns_none():
    assert extract_email("Thanks for your time today.") is None
    assert extract_email("I'll send that through shortly.") is None


def test_normalize_email_is_case_and_space_insensitive():
    assert normalize_email("  James.Whitfield@Gmail.COM ") == "james.whitfield@gmail.com"


@pytest.mark.parametrize(
    "text,expected",
    [
        ("Your peak rate is thirty-one point nine cents", 31.9),
        ("the rate is thirty-three point one four cents per kilowatt hour", 33.14),
        ("Our peak rate is 33.14 c/kWh", 33.14),
        ("the daily supply charge is ninety eight point seven cents", 98.7),
        ("that's one hundred and one point two cents", 101.2),
    ],
)
def test_spoken_numbers_parse_to_decimals(text, expected):
    reading = extract_numeric(text)
    assert reading is not None
    assert reading.value == pytest.approx(expected)


def test_numeric_keyword_scoping_ignores_unrelated_numbers():
    text = "You're on the Saver 5 plan, and the peak rate is 33.14 cents."
    reading = extract_numeric(text, keywords=["peak rate"])
    assert reading is not None
    assert reading.value == pytest.approx(33.14)


def test_dollars_convert_to_cents_when_rate_card_is_in_cents():
    reading = NumericReading(value=0.3314, spoken=True, currency_hint="DOLLARS")
    assert convert_to_unit(reading, "c/kWh") == pytest.approx(33.14)


@pytest.mark.parametrize(
    "text,expected",
    [
        ("my date of birth is the twelfth of March nineteen eighty-five", date(1985, 3, 12)),
        ("date of birth is the twenty-sixth of November nineteen ninety-one", date(1991, 11, 26)),
        ("born on the thirty-first of December nineteen ninety", date(1990, 12, 31)),
        ("moving in on 01/10/2026", date(2026, 10, 1)),
        ("move-in date of 1st October 2026", date(2026, 10, 1)),
    ],
)
def test_spoken_dates_normalize(text, expected):
    assert extract_date(text) == expected


def test_date_without_year_uses_reference_year():
    assert extract_date("I'm moving in on the first of October", reference_year=2026) == date(2026, 10, 1)


def test_identifier_normalization_preserves_value():
    assert normalize_identifier("6102 0012-34") == "6102001234"
    assert compare_identifiers("6102 0012 34", "6102001234") is True


def test_spoken_identifier_digits():
    text = "the NMI is six one zero two zero zero one two three four"
    assert extract_identifier(text, min_length=10, expected="6102001234") == "6102001234"


def test_identifier_ignores_short_incidental_numbers():
    assert extract_identifier("I'm on plan 5 at number 12", min_length=10) is None


def test_phone_normalization_handles_australian_forms():
    assert normalize_phone("+61 412 555 108") == "0412555108"
    assert normalize_phone("(04) 1255 5108") == "0412555108"


def test_boolean_extraction_is_conservative():
    assert extract_boolean("No, nobody here is on life support.") is False
    assert extract_boolean("Yes, that's correct.") is True
    # Contradictory and hedged answers must not resolve to a value.
    assert extract_boolean("No, that's correct") is None
    assert extract_boolean("I think so, probably") is None


def test_payment_data_is_redacted():
    redacted = redact_sensitive_data("My card is 4111 1111 1111 1111, expiry 09/27, CVV 123.")
    assert "4111" not in redacted
    assert "123" not in redacted
    assert "[REDACTED]" in redacted
