"""Boolean normalisation for clear yes/no phrasing.

Only unambiguous phrases map to a value. Anything hedged ("I think so",
"probably") returns None, which callers must treat as UNCERTAIN rather than
guessing.
"""

from __future__ import annotations

import re

from app.services.normalization.words import FALSE_PHRASES, TRUE_PHRASES


def extract_boolean(text: str) -> bool | None:
    # Punctuation becomes whitespace so " no, nobody..." still matches " no ".
    cleaned = re.sub(r"[,.;:!?]", " ", text.lower())
    lowered = " " + re.sub(r"\s+", " ", cleaned).strip() + " "

    # Longest phrases first so "that's not right" beats "right".
    negative = any(f" {phrase} " in lowered for phrase in sorted(FALSE_PHRASES, key=len, reverse=True))
    positive = any(f" {phrase} " in lowered for phrase in sorted(TRUE_PHRASES, key=len, reverse=True))

    # Both readings present ("no, that's correct") is ambiguous, and an
    # ambiguous answer must not be resolved by guessing.
    if negative == positive:
        return None
    return not negative


def normalize_boolean(value: object) -> bool | None:
    if isinstance(value, bool):
        return value
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return bool(value)
    text = str(value).strip().lower()
    if text in {"true", "yes", "y", "1"}:
        return True
    if text in {"false", "no", "n", "0"}:
        return False
    return extract_boolean(text)


def compare_booleans(observed: bool, expected: bool) -> bool:
    return observed is expected
