"""Text normalisation and phrase matching for VERBATIM checks."""

from __future__ import annotations

import re

from app.services.normalization.numeric import parse_spoken_number
from app.services.normalization.words import DECIMAL_MARKERS, MAGNITUDE_WORDS, TENS_WORDS, UNIT_WORDS

# "for", "o" and "oh" are digit words when reading out an NMI but ordinary
# English everywhere else, so they are never turned into digits in prose.
_PROSE_NUMBER_WORDS = (set(UNIT_WORDS) | set(TENS_WORDS)) - {"for", "o", "oh", "nought"}

# A phrase this long cannot plausibly match by accident once spaces are
# ignored, which is what makes the run-together fallback safe.
MIN_SPACELESS_MATCH_CHARS = 24


def normalize_text(value: str) -> str:
    """Lower-case, strip punctuation, collapse whitespace.

    Used for NORMALIZED_TEXT comparison so "This call may be recorded,
    monitored..." matches the approved script despite punctuation drift.
    """
    lowered = value.lower()
    lowered = re.sub(r"[^\w\s]", " ", lowered)
    return re.sub(r"\s+", " ", lowered).strip()


def words_to_digits(normalized: str) -> str:
    """Rewrite runs of number words as digits ("fourteen rosella" -> "14 rosella").

    Applied to BOTH sides of a comparison, so it can only make equivalent
    spellings meet ("14 Rosella Street" heard as "fourteen Rosella Street"),
    never make different text match.
    """
    tokens = normalized.split()
    out: list[str] = []
    index = 0
    while index < len(tokens):
        if tokens[index] not in _PROSE_NUMBER_WORDS:
            out.append(tokens[index])
            index += 1
            continue
        run = [tokens[index]]
        cursor = index + 1
        while cursor < len(tokens) and (
            tokens[cursor] in _PROSE_NUMBER_WORDS
            or tokens[cursor] in MAGNITUDE_WORDS
            or (tokens[cursor] == "and" and cursor + 1 < len(tokens) and tokens[cursor + 1] in _PROSE_NUMBER_WORDS)
            or (
                tokens[cursor] in DECIMAL_MARKERS
                and cursor + 1 < len(tokens)
                and tokens[cursor + 1] in _PROSE_NUMBER_WORDS
            )
        ):
            run.append(tokens[cursor])
            cursor += 1
        value = parse_spoken_number(run)
        if value is None:
            out.append(tokens[index])
            index += 1
            continue
        out.append(str(int(value)) if float(value).is_integer() else str(value))
        index = cursor
    return " ".join(out)


def normalize_for_phrase(value: str) -> str:
    return words_to_digits(normalize_text(value))


def compare_exact_text(observed: str, expected: str) -> bool:
    return observed.strip() == expected.strip()


def contains_exact_phrase(haystack: str, phrase: str) -> bool:
    return phrase.strip() in haystack


def contains_normalized_phrase(haystack: str, phrase: str) -> bool:
    normalized_phrase = normalize_for_phrase(phrase)
    return bool(normalized_phrase) and normalized_phrase in normalize_for_phrase(haystack)


def contains_phrase_ignoring_spacing(haystack: str, phrase: str) -> bool:
    """Match after removing all spaces.

    Speech-to-text often runs words together ("assuranceand, training"). Used
    only as a fallback after the normal match fails, and only for phrases long
    enough that an accidental match is not realistic.
    """
    squashed_phrase = normalize_for_phrase(phrase).replace(" ", "")
    if len(squashed_phrase) < MIN_SPACELESS_MATCH_CHARS:
        return False
    return squashed_phrase in normalize_for_phrase(haystack).replace(" ", "")


def token_coverage(haystack: str, phrase: str) -> float:
    """Fraction of the required phrase's tokens present in the text.

    Reported on verbatim failures so a reviewer can tell "agent said nothing
    like this" (near 0) from "agent paraphrased it" (near 1) without reading
    the whole transcript.
    """
    phrase_tokens = normalize_for_phrase(phrase).split()
    if not phrase_tokens:
        return 0.0
    haystack_tokens = set(normalize_for_phrase(haystack).split())
    hits = sum(1 for token in phrase_tokens if token in haystack_tokens)
    return hits / len(phrase_tokens)
