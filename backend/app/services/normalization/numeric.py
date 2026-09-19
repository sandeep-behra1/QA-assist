"""Numeric normalisation, including spoken numbers.

Handles both written ("$0.45", "33.14 cents") and spoken ("thirty-three
point one four") forms. Decimal digits after "point" are read individually,
which is how people actually say rates: "thirty-three point one four" is
33.14, not 33.5.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from app.services.normalization.words import (
    DECIMAL_MARKERS,
    DIGIT_WORDS,
    MAGNITUDE_WORDS,
    TENS_WORDS,
    UNIT_WORDS,
)

_WRITTEN_NUMBER_RE = re.compile(r"(?<![\w.])(\d{1,3}(?:,\d{3})*(?:\.\d+)?|\d+(?:\.\d+)?)(?![\w])")
_TOKEN_SPLIT_RE = re.compile(r"[\s\-]+")

CENTS_UNITS = {"c/kwh", "c/kWh".lower(), "cents", "cent", "c"}
DOLLAR_UNITS = {"$/kwh", "dollars", "dollar", "aud", "$"}


@dataclass(frozen=True)
class NumericReading:
    value: float
    spoken: bool
    currency_hint: str | None  # "CENTS" | "DOLLARS" | None


def _clean_tokens(text: str) -> list[str]:
    lowered = text.lower().replace("-", " ")
    tokens = [t.strip(",.!?;:()\"'") for t in _TOKEN_SPLIT_RE.split(lowered)]
    return [t for t in tokens if t]


def parse_spoken_number(tokens: list[str]) -> float | None:
    """Parse a contiguous run of number words into a float.

    Returns None when the tokens do not form a number.
    """
    if not tokens:
        return None

    integer_tokens: list[str] = []
    decimal_tokens: list[str] = []
    seen_decimal_marker = False
    for token in tokens:
        if token in DECIMAL_MARKERS:
            if seen_decimal_marker:
                break
            seen_decimal_marker = True
            continue
        if seen_decimal_marker:
            decimal_tokens.append(token)
        else:
            integer_tokens.append(token)

    integer_value = _parse_integer_words(integer_tokens)
    if integer_value is None and not decimal_tokens:
        return None
    if integer_value is None:
        integer_value = 0

    if not decimal_tokens:
        return float(integer_value)

    # Digits after "point" are spoken one at a time: "one four" -> .14
    digits = ""
    for token in decimal_tokens:
        if token.isdigit():
            digits += token
        elif token in DIGIT_WORDS:
            digits += str(DIGIT_WORDS[token])
        else:
            break
    if not digits:
        return float(integer_value)
    return float(f"{integer_value}.{digits}")


def _parse_integer_words(tokens: list[str]) -> int | None:
    if not tokens:
        return None
    total = 0
    current = 0
    matched = False
    for token in tokens:
        if token.isdigit():
            current += int(token)
            matched = True
        elif token in UNIT_WORDS:
            current += UNIT_WORDS[token]
            matched = True
        elif token in TENS_WORDS:
            current += TENS_WORDS[token]
            matched = True
        elif token in MAGNITUDE_WORDS:
            magnitude = MAGNITUDE_WORDS[token]
            if magnitude == 100:
                current = (current or 1) * 100
            else:
                total += (current or 1) * magnitude
                current = 0
            matched = True
        elif token == "and" and matched:
            continue
        else:
            break
    if not matched:
        return None
    return total + current


def _currency_hint(text: str) -> str | None:
    lowered = text.lower()
    if "cent" in lowered or re.search(r"\bc\s*/\s*kwh\b", lowered):
        return "CENTS"
    if "$" in lowered or "dollar" in lowered:
        return "DOLLARS"
    return None


def extract_numeric(text: str, keywords: list[str] | None = None) -> NumericReading | None:
    """Extract a numeric reading from free text.

    When ``keywords`` are supplied, only the clause(s) mentioning one of them
    are searched, so an unrelated number elsewhere in the sentence (a plan
    name, a phone number) cannot be mistaken for the value under test.
    """
    scope = _scope_text(text, keywords)
    if scope is None:
        return None

    written = _WRITTEN_NUMBER_RE.search(scope)
    if written:
        raw = written.group(1).replace(",", "")
        return NumericReading(value=float(raw), spoken=False, currency_hint=_currency_hint(scope))

    tokens = _clean_tokens(scope)
    for start in range(len(tokens)):
        if tokens[start] not in UNIT_WORDS and tokens[start] not in TENS_WORDS:
            continue
        run: list[str] = []
        for token in tokens[start:]:
            if (
                token in UNIT_WORDS
                or token in TENS_WORDS
                or token in MAGNITUDE_WORDS
                or token in DECIMAL_MARKERS
                or token == "and"
                or token.isdigit()
            ):
                run.append(token)
            else:
                break
        value = parse_spoken_number(run)
        if value is not None:
            return NumericReading(value=value, spoken=True, currency_hint=_currency_hint(scope))
    return None


def _scope_text(text: str, keywords: list[str] | None) -> str | None:
    if not keywords:
        return text
    clauses = re.split(r"(?<=[.!?,])\s+", text)
    matching = [c for c in clauses if any(k.lower() in c.lower() for k in keywords)]
    if not matching:
        return None
    return " ".join(matching)


def convert_to_unit(reading: NumericReading, target_unit: str | None) -> float:
    """Reconcile a spoken currency with the rate card's unit.

    Energy rates are quoted in c/kWh but agents sometimes say dollars. If the
    target unit is cents and the speaker clearly said dollars, scale up (and
    vice versa). When the speaker gave no currency cue, the number is taken
    at face value in the target unit.
    """
    if not target_unit:
        return reading.value
    unit = target_unit.strip().lower()
    if unit in CENTS_UNITS and reading.currency_hint == "DOLLARS":
        return reading.value * 100
    if unit in DOLLAR_UNITS and reading.currency_hint == "CENTS":
        return reading.value / 100
    return reading.value


def normalize_numeric_value(value: str | float | int) -> float | None:
    if isinstance(value, (int, float)):
        return float(value)
    reading = extract_numeric(str(value))
    return reading.value if reading else None


def compare_numeric(observed: float, expected: float, tolerance: float = 0.0) -> bool:
    return abs(observed - expected) <= tolerance
