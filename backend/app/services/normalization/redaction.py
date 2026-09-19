"""Redaction of sensitive payment data.

Applied once, at transcript ingest, so no downstream consumer -- scoring,
evidence, the LLM prompt, the API, the UI -- can ever see a card number.
"""

from __future__ import annotations

import re

REDACTION_TOKEN = "[REDACTED]"

_CARD_RE = re.compile(r"\b(?:\d[ \-]?){13,19}\b")
_CVV_RE = re.compile(r"\b(?:cvv|cvc|security code)\D{0,10}?(\d{3,4})\b", re.IGNORECASE)
_OTP_WORDS_RE = re.compile(
    r"\b((?:otp|passcode|pass code|verification code|security code|one[- ]time (?:code|password|pin)|"
    r"text message code|sms code|code)\b[^0-9\n]{0,25}?)"
    r"((?:(?:zero|oh|one|two|three|four|five|six|seven|eight|nine)[\s\-]+){3,7}"
    r"(?:zero|oh|one|two|three|four|five|six|seven|eight|nine))\b",
    re.IGNORECASE,
)
_EXPIRY_RE = re.compile(r"\b(0[1-9]|1[0-2])\s*/\s*(\d{2}|\d{4})\b")
# One-time passcodes read aloud on a recorded line ("the code is 4 8 2 9 1 3").
# A code that is on the recording is a credential; it must not reach scoring,
# the LLM, the API or the UI.
_OTP_RE = re.compile(
    r"\b((?:otp|passcode|pass code|verification code|security code|one[- ]time (?:code|password|pin)|"
    r"text message code|sms code|code)\b[^0-9\n]{0,25})((?:\d[\s\-]?){4,8})(?!\d)",
    re.IGNORECASE,
)


def redact_sensitive_data(text: str) -> str:
    redacted = _OTP_RE.sub(lambda m: m.group(1) + REDACTION_TOKEN, text)
    redacted = _OTP_WORDS_RE.sub(lambda m: m.group(1) + REDACTION_TOKEN, redacted)
    redacted = _CARD_RE.sub(REDACTION_TOKEN, redacted)
    redacted = _CVV_RE.sub(lambda m: m.group(0).replace(m.group(1), REDACTION_TOKEN), redacted)
    return _EXPIRY_RE.sub(REDACTION_TOKEN, redacted)
