"""Redaction of sensitive payment data.

Applied once, at transcript ingest, so no downstream consumer -- scoring,
evidence, the LLM prompt, the API, the UI -- can ever see a card number.
"""

from __future__ import annotations

import re

REDACTION_TOKEN = "[REDACTED]"

_CARD_RE = re.compile(r"\b(?:\d[ \-]?){13,19}\b")
_CVV_RE = re.compile(r"\b(?:cvv|cvc|security code)\D{0,10}?(\d{3,4})\b", re.IGNORECASE)
_EXPIRY_RE = re.compile(r"\b(0[1-9]|1[0-2])\s*/\s*(\d{2}|\d{4})\b")


def redact_sensitive_data(text: str) -> str:
    redacted = _CARD_RE.sub(REDACTION_TOKEN, text)
    redacted = _CVV_RE.sub(lambda m: m.group(0).replace(m.group(1), REDACTION_TOKEN), redacted)
    return _EXPIRY_RE.sub(REDACTION_TOKEN, redacted)
