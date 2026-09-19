"""Identifier normalisation (NMI, MIRN, account numbers).

Formatting is stripped but the underlying value is never altered: spaces,
hyphens and spoken digit groups are removed, letters are upper-cased, and
nothing is padded, truncated or re-ordered.
"""

from __future__ import annotations

import re

from app.services.normalization.words import DIGIT_WORDS, TEEN_WORDS, TENS_WORDS

_FORMATTING_RE = re.compile(r"[\s\-_.]")

# "double seven" -> "77", "triple three" -> "333"
_REPEATERS = {"double": 2, "triple": 3, "treble": 3}


def normalize_identifier(value: str) -> str:
    return _FORMATTING_RE.sub("", value.strip()).upper()


def extract_identifier(text: str, min_length: int = 6, expected: str | None = None) -> str | None:
    """Pull an identifier out of free text, written or spoken digit-by-digit.

    ``min_length`` filters out incidental short numbers. ``expected`` is used
    only to pick between multiple equally valid candidates -- it can never
    manufacture a value that was not actually present in the text.
    """
    candidates: list[str] = []

    for raw in re.findall(r"\b[0-9][0-9\s\-]{%d,}[0-9]\b" % max(min_length - 2, 1), text):
        normalized = normalize_identifier(raw)
        if len(normalized) >= min_length:
            candidates.append(normalized)

    spoken = _extract_spoken_digits(text)
    if spoken and len(spoken) >= min_length:
        candidates.append(spoken)

    if not candidates:
        return None
    if expected:
        normalized_expected = normalize_identifier(expected)
        for candidate in candidates:
            if candidate == normalized_expected:
                return candidate
    return candidates[0]


def _extract_spoken_digits(text: str) -> str | None:
    tokens = re.split(r"[\s\-]+", text.lower())
    tokens = [t.strip(",.!?;:") for t in tokens if t.strip(",.!?;:")]

    best = ""
    current = ""
    pending_repeat = 0
    for token in tokens:
        if token in _REPEATERS:
            pending_repeat = _REPEATERS[token]
            continue
        digit = _token_to_digits(token)
        if digit is None:
            if len(current) > len(best):
                best = current
            current = ""
            pending_repeat = 0
            continue
        if pending_repeat:
            current += digit * pending_repeat
            pending_repeat = 0
        else:
            current += digit
    if len(current) > len(best):
        best = current
    return best or None


def _token_to_digits(token: str) -> str | None:
    if token.isdigit():
        return token
    if token in DIGIT_WORDS:
        return str(DIGIT_WORDS[token])
    if token in TEEN_WORDS:
        return str(TEEN_WORDS[token])
    if token in TENS_WORDS:
        return str(TENS_WORDS[token])
    return None


def compare_identifiers(observed: str, expected: str) -> bool:
    return normalize_identifier(observed) == normalize_identifier(expected)
