"""Numeric normalisation, including spoken numbers.

Handles both written ("$0.45", "33.14 cents") and spoken ("thirty-three
point one four") forms. Decimal digits after "point" are read individually,
which is how people actually say rates: "thirty-three point one four" is
33.14, not 33.5.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, replace

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
    # True when the figure was stated approximately or as a range ("around
    # 33 to 34 cents"). A hedged figure is never verified, only escalated.
    hedged: bool = False


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


# ---------------------------------------------------------------------------
# Candidate extraction (used by the FACTUAL evaluators)
#
# extract_numeric() above returns the first number it sees, which is fine for
# tidy text but is a false-pass hazard on real speech: "33.14 cents for twelve
# months" or "around thirty-three to thirty-four cents" contain several
# numbers, and picking one silently is exactly how a wrong value slips
# through. This path returns EVERY plausible candidate, keeps only numbers
# that carry a rate unit, and lets the caller treat more than one distinct
# value as a conflict (UNCERTAIN).
# ---------------------------------------------------------------------------

_NUMBER_WORDS_STANDALONE = (set(UNIT_WORDS) | set(TENS_WORDS)) - {"for", "o", "oh", "nought"}
_DECIMAL_DIGIT_WORDS = set(DIGIT_WORDS) - {"for"}

_ACCEPTED_UNITS = {"c", "c/kwh", "cent", "cents", "dollar", "dollars", "kwh", "aud"}
_PER_QUALIFIERS = {"kilowatt", "kilowatts", "kwh", "kw", "day", "month"}

_CANDIDATE_RE = re.compile(r"(?<![\w.])(?P<dollar>\$\s*)?(?P<num>\d+(?:,\d{3})*(?:\.\d+)?)")
_FOLLOWING_WORDS_RE = re.compile(r"\s*([A-Za-z/%]+)(?:\s+([A-Za-z]+))?")

_AND_SPLIT_RE = re.compile(
    r"\s+(?:and|but)\s+(?!(?:%s)\b|\d)" % "|".join(sorted(_NUMBER_WORDS_STANDALONE | set(DECIMAL_MARKERS))),
    re.IGNORECASE,
)


def _scope_clauses(text: str, keywords: list[str] | None) -> list[tuple[str, bool]] | None:
    """Clauses to search, each with whether its whole SENTENCE was hedged.

    Splitting on "and" (except inside a spoken number such as "one hundred and
    one") keeps "peak rate is 33.14 cents and off-peak is 23.10 cents" from
    putting both figures in one clause. Hedging is judged before that split,
    on the sentence, because "between thirty-three and thirty-four cents"
    would otherwise lose its hedge word to the split.
    """
    from app.services.normalization.keywords import contains_any_keyword

    clauses: list[tuple[str, bool]] = []
    for sentence in re.split(r"(?<=[.!?,;])\s+", text):
        hedged = _is_hedged(sentence)
        clauses.extend((part, hedged) for part in _AND_SPLIT_RE.split(sentence) if part.strip())
    if not keywords:
        return clauses
    matching = [item for item in clauses if contains_any_keyword(item[0], keywords)]
    return matching or None


_NUMBERISH = r"(?:\d|%s)" % "|".join(sorted(_NUMBER_WORDS_STANDALONE))
_HEDGE_RE = re.compile(
    r"\b(?:around|about|roughly|approximately|approx|somewhere|between|ish|or so|up to|from)\b", re.IGNORECASE
)
_RANGE_RE = re.compile(
    rf"\b{_NUMBERISH}[\w.,\-]*\s*(?:cents?|dollars?|c)?\s+(?:to|or|until)\s+{_NUMBERISH}", re.IGNORECASE
)


def _is_hedged(clause: str) -> bool:
    return bool(_HEDGE_RE.search(clause) or _RANGE_RE.search(clause))


def _unit_is_accepted(first: str | None, second: str | None) -> bool:
    if not first:
        return False
    word = first.lower()
    if word in _ACCEPTED_UNITS:
        return True
    # "per kilowatt hour" is a rate; "per cent" is a percentage and is not.
    return word == "per" and (second or "").lower() in _PER_QUALIFIERS


def _hint_from_unit(first: str | None, dollar: bool) -> str | None:
    if dollar:
        return "DOLLARS"
    word = (first or "").lower()
    if word in {"c", "c/kwh", "cent", "cents"}:
        return "CENTS"
    if word in {"dollar", "dollars", "aud"}:
        return "DOLLARS"
    return None


def extract_numeric_candidates(text: str, keywords: list[str] | None = None) -> list[NumericReading]:
    """Every number in the keyword-matching clauses that carries a rate unit."""
    clauses = _scope_clauses(text, keywords)
    if not clauses:
        return []

    readings: list[NumericReading] = []
    for clause, sentence_hedged in clauses:
        clause_readings: list[NumericReading] = []
        for match in _CANDIDATE_RE.finditer(clause):
            following = _FOLLOWING_WORDS_RE.match(clause, match.end())
            first, second = (following.group(1), following.group(2)) if following else (None, None)
            dollar = bool(match.group("dollar"))
            if not (dollar or _unit_is_accepted(first, second)):
                continue
            clause_readings.append(
                NumericReading(
                    value=float(match.group("num").replace(",", "")),
                    spoken=False,
                    currency_hint=_hint_from_unit(first, dollar),
                )
            )
        clause_readings.extend(_spoken_candidates(clause))
        if clause_readings and (sentence_hedged or _is_hedged(clause)):
            clause_readings = [replace(r, hedged=True) for r in clause_readings]
        readings.extend(clause_readings)
    return readings


def _spoken_candidates(clause: str) -> list[NumericReading]:
    tokens = _clean_tokens(clause)
    readings: list[NumericReading] = []
    index = 0
    while index < len(tokens):
        if tokens[index] not in _NUMBER_WORDS_STANDALONE:
            index += 1
            continue

        run: list[str] = []
        seen_point = False
        cursor = index
        while cursor < len(tokens):
            token = tokens[cursor]
            if not seen_point and token in DECIMAL_MARKERS:
                seen_point = True
            elif seen_point and (token in _DECIMAL_DIGIT_WORDS or token.isdigit()):
                pass
            elif not seen_point and (
                token in _NUMBER_WORDS_STANDALONE
                or token in MAGNITUDE_WORDS
                or token.isdigit()
                or (token == "and" and cursor + 1 < len(tokens) and tokens[cursor + 1] in _NUMBER_WORDS_STANDALONE)
            ):
                pass
            else:
                break
            run.append(token)
            cursor += 1

        first = tokens[cursor] if cursor < len(tokens) else None
        second = tokens[cursor + 1] if cursor + 1 < len(tokens) else None
        value = parse_spoken_number(run)
        if value is not None and _unit_is_accepted(first, second):
            readings.append(
                NumericReading(value=value, spoken=True, currency_hint=_hint_from_unit(first, False))
            )
        index = max(cursor, index + 1)
    return readings


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
