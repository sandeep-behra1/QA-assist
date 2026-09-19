"""Phone normalisation (Australian conventions)."""

from __future__ import annotations

import re

from app.services.normalization.identifier import _extract_spoken_digits


def normalize_phone(value: str) -> str:
    digits = re.sub(r"\D", "", value)
    if digits.startswith("61") and len(digits) == 11:
        digits = "0" + digits[2:]
    elif len(digits) == 9 and not digits.startswith("0"):
        digits = "0" + digits
    return digits


def extract_phone(text: str) -> str | None:
    written = re.search(r"(\+?\d[\d\s\-()]{7,}\d)", text)
    if written:
        normalized = normalize_phone(written.group(1))
        if len(normalized) >= 8:
            return normalized
    spoken = _extract_spoken_digits(text)
    if spoken and len(spoken) >= 8:
        return normalize_phone(spoken)
    return None


def compare_phones(observed: str, expected: str) -> bool:
    return normalize_phone(observed) == normalize_phone(expected)
