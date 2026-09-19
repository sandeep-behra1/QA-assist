"""Date normalisation for spoken and written Australian date forms.

Only unambiguous readings are returned. Ambiguity (e.g. a bare "3/4/26"
where day/month order cannot be trusted) is resolved with the AU convention
(day first), which is stated explicitly rather than guessed per-input.
"""

from __future__ import annotations

import re
from datetime import date

from app.services.normalization.numeric import _parse_integer_words
from app.services.normalization.words import MONTHS, ORDINAL_WORDS, TENS_WORDS, UNIT_WORDS

_NUMERIC_DATE_RE = re.compile(r"\b(\d{1,2})[/\-.](\d{1,2})[/\-.](\d{2,4})\b")
_ISO_DATE_RE = re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b")
_DAY_MONTH_YEAR_RE = re.compile(
    r"\b(\d{1,2})(?:st|nd|rd|th)?\s+(?:of\s+)?([a-z]+),?\s*(\d{4})?\b", re.IGNORECASE
)
_MONTH_DAY_YEAR_RE = re.compile(
    r"\b([a-z]+)\s+(\d{1,2})(?:st|nd|rd|th)?,?\s*(\d{4})?\b", re.IGNORECASE
)


def _normalize_year(raw: int, default_century: int = 2000) -> int:
    if raw >= 1000:
        return raw
    return default_century + raw


# "nineteen eighty-five" = 1900 + 85, "twenty twenty-six" = 2000 + 26.
_CENTURY_WORDS = {"eighteen": 1800, "nineteen": 1900, "twenty": 2000}


def _spoken_year(text: str) -> int | None:
    """Parse "twenty twenty six" / "nineteen eighty-five" / "two thousand and twenty six"."""
    tokens = re.split(r"[\s\-]+", text.lower().strip())
    tokens = [t.strip(",.") for t in tokens if t.strip(",.")]
    if not tokens:
        return None

    if tokens[0] in _CENTURY_WORDS and len(tokens) >= 2:
        remainder = _parse_integer_words(tokens[1:])
        if remainder is not None and 0 <= remainder <= 99:
            return _CENTURY_WORDS[tokens[0]] + remainder
    value = _parse_integer_words(tokens)
    if value is not None and 1900 <= value <= 2100:
        return value
    return None


def _spoken_day(text: str) -> int | None:
    """Parse a day-of-month: "3", "3rd", "third", "twenty-sixth", "thirty first"."""
    token = text.lower().strip()
    if token in ORDINAL_WORDS:
        return ORDINAL_WORDS[token]

    stripped = re.sub(r"(st|nd|rd|th)$", "", token)
    if stripped.isdigit():
        day = int(stripped)
        return day if 1 <= day <= 31 else None

    # Compound ordinals combine a tens word with an ordinal unit.
    total = 0
    matched = False
    for part in re.split(r"[\s\-]+", token):
        if not part:
            continue
        if part in TENS_WORDS:
            total += TENS_WORDS[part]
        elif part in ORDINAL_WORDS:
            total += ORDINAL_WORDS[part]
        elif part in UNIT_WORDS:
            total += UNIT_WORDS[part]
        else:
            return None
        matched = True
    return total if matched and 1 <= total <= 31 else None


def extract_date(text: str, reference_year: int | None = None) -> date | None:
    """Extract a single unambiguous date from free text."""
    iso = _ISO_DATE_RE.search(text)
    if iso:
        return _safe_date(int(iso.group(1)), int(iso.group(2)), int(iso.group(3)))

    numeric = _NUMERIC_DATE_RE.search(text)
    if numeric:
        day, month, year = (int(numeric.group(1)), int(numeric.group(2)), int(numeric.group(3)))
        return _safe_date(_normalize_year(year), month, day)

    lowered = text.lower()

    spoken = _extract_spoken_date(lowered, reference_year)
    if spoken:
        return spoken

    day_first = _DAY_MONTH_YEAR_RE.search(lowered)
    if day_first and day_first.group(2) in MONTHS:
        day = int(day_first.group(1))
        month = MONTHS[day_first.group(2)]
        year = int(day_first.group(3)) if day_first.group(3) else reference_year
        if year:
            return _safe_date(year, month, day)

    month_first = _MONTH_DAY_YEAR_RE.search(lowered)
    if month_first and month_first.group(1) in MONTHS:
        month = MONTHS[month_first.group(1)]
        day = int(month_first.group(2))
        year = int(month_first.group(3)) if month_first.group(3) else reference_year
        if year:
            return _safe_date(year, month, day)
    return None


def _extract_spoken_date(lowered: str, reference_year: int | None) -> date | None:
    """Handle "the first of October twenty twenty-six"."""
    for month_name, month in MONTHS.items():
        # Capture a short window before the month so multi-word days like
        # "twenty sixth" survive, then narrow it down to the day itself.
        pattern = re.compile(
            rf"\b((?:[a-z0-9\-]+\s+){{0,2}}[a-z0-9\-]+)\s+(?:of\s+)?{month_name}\b(?:\s*,?\s*(.+))?",
            re.IGNORECASE,
        )
        match = pattern.search(lowered)
        if not match:
            continue
        day = _day_from_window(match.group(1))
        if day is None:
            continue
        year = reference_year
        tail = (match.group(2) or "").strip()
        if tail:
            year_tokens = re.split(r"\s+", tail)[:4]
            parsed_year = _spoken_year(" ".join(year_tokens))
            if parsed_year:
                year = parsed_year
        if year:
            return _safe_date(year, month, day)
    return None


def _day_from_window(window: str) -> int | None:
    """Pick the day out of the words immediately preceding a month name.

    Tries the longest trailing phrase first so "the twenty sixth" resolves to
    26 rather than 6.
    """
    tokens = [t for t in re.split(r"\s+", window.strip()) if t]
    # The window may end on filler ("the first of" | September); drop it so
    # the day itself is the trailing token.
    while tokens and tokens[-1] in {"of", "the"}:
        tokens.pop()
    for size in (2, 1):
        if len(tokens) >= size:
            day = _spoken_day(" ".join(tokens[-size:]))
            if day is not None:
                return day
    return None


def _safe_date(year: int, month: int, day: int) -> date | None:
    try:
        return date(year, month, day)
    except ValueError:
        return None


def compare_dates(observed: date, expected: date) -> bool:
    return observed == expected
