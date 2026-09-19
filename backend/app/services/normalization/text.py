"""Text normalisation and phrase matching for VERBATIM checks."""

from __future__ import annotations

import re


def normalize_text(value: str) -> str:
    """Lower-case, strip punctuation, collapse whitespace.

    Used for NORMALIZED_TEXT comparison so "This call may be recorded,
    monitored..." matches the approved script despite punctuation drift.
    """
    lowered = value.lower()
    lowered = re.sub(r"[^\w\s]", " ", lowered)
    return re.sub(r"\s+", " ", lowered).strip()


def compare_exact_text(observed: str, expected: str) -> bool:
    return observed.strip() == expected.strip()


def contains_exact_phrase(haystack: str, phrase: str) -> bool:
    return phrase.strip() in haystack


def contains_normalized_phrase(haystack: str, phrase: str) -> bool:
    normalized_phrase = normalize_text(phrase)
    return bool(normalized_phrase) and normalized_phrase in normalize_text(haystack)


def token_coverage(haystack: str, phrase: str) -> float:
    """Fraction of the required phrase's tokens present in the text.

    Reported on verbatim failures so a reviewer can tell "agent said nothing
    like this" (near 0) from "agent paraphrased it" (near 1) without reading
    the whole transcript.
    """
    phrase_tokens = normalize_text(phrase).split()
    if not phrase_tokens:
        return 0.0
    haystack_tokens = set(normalize_text(haystack).split())
    hits = sum(1 for token in phrase_tokens if token in haystack_tokens)
    return hits / len(phrase_tokens)
