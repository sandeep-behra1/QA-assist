"""Email normalisation from written and spoken forms.

Deliberately token-based rather than one big regex: real agents say
"john dot smith at g mail dot com", which no single pattern handles well.
The algorithm anchors on the "at"/"@" token and walks outward through
email-shaped tokens, stopping at ordinary conversational words.
"""

from __future__ import annotations

import re

WRITTEN_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")
_VALID_EMAIL_RE = re.compile(r"^[a-z0-9._%+\-]+@[a-z0-9.\-]+\.[a-z]{2,}$")

SEPARATOR_WORDS = {
    "dot": ".",
    "point": ".",
    "period": ".",
    "underscore": "_",
    "dash": "-",
    "hyphen": "-",
    "minus": "-",
    "plus": "+",
}

AT_WORDS = {"at", "@"}

# Providers are routinely spoken as two words.
PROVIDER_FIXUPS = [
    ("g mail", "gmail"),
    ("gee mail", "gmail"),
    ("hot mail", "hotmail"),
    ("out look", "outlook"),
    ("i cloud", "icloud"),
    ("y mail", "ymail"),
    ("bigpond", "bigpond"),
    ("big pond", "bigpond"),
    ("opton us", "optusnet"),
    ("optus net", "optusnet"),
]

# Words that can never be part of an address; used as walk boundaries.
STOP_WORDS = {
    "is",
    "it",
    "its",
    "it's",
    "email",
    "e-mail",
    "address",
    "the",
    "my",
    "your",
    "you",
    "to",
    "be",
    "that",
    "this",
    "confirm",
    "confirmed",
    "have",
    "has",
    "on",
    "file",
    "sure",
    "yes",
    "yeah",
    "no",
    "okay",
    "ok",
    "and",
    "so",
    "um",
    "uh",
    "spelled",
    "spelt",
    "correct",
    "right",
    "please",
    "can",
    "i",
    "just",
    "we",
    "got",
    "record",
    "records",
    "for",
    "of",
    "a",
    "all",
    "lowercase",
    "thanks",
    "thank",
    "great",
    "perfect",
    "send",
    "sending",
    "details",
    "welcome",
    "pack",
}


def normalize_email(value: str) -> str:
    """Canonicalise an already-assembled address (lowercase, no spaces)."""
    return re.sub(r"\s+", "", value.strip().lower())


def _apply_provider_fixups(text: str) -> str:
    lowered = text.lower()
    for spoken, canonical in PROVIDER_FIXUPS:
        lowered = re.sub(rf"\b{re.escape(spoken)}\b", canonical, lowered)
    return lowered


def _tokenize(text: str) -> list[str]:
    cleaned = _apply_provider_fixups(text)
    raw = re.split(r"\s+", cleaned)
    return [t.strip(",;:!?()\"'") for t in raw if t.strip(",;:!?()\"'")]


def _is_email_token(token: str) -> bool:
    if token in SEPARATOR_WORDS or token in AT_WORDS:
        return True
    if token in STOP_WORDS:
        return False
    return bool(re.fullmatch(r"[a-z0-9._%+\-]+", token))


def extract_email(text: str) -> str | None:
    """Find and canonicalise the first email address in free text."""
    written = WRITTEN_EMAIL_RE.search(text)
    if written:
        candidate = normalize_email(written.group(0).rstrip("."))
        return candidate if _VALID_EMAIL_RE.fullmatch(candidate) else None

    tokens = _tokenize(text)
    for index, token in enumerate(tokens):
        if token not in AT_WORDS:
            continue

        left: list[str] = []
        for previous in reversed(tokens[:index]):
            if not _is_email_token(previous) or previous in AT_WORDS:
                break
            left.append(previous)
        left.reverse()

        right: list[str] = []
        for following in tokens[index + 1 :]:
            if not _is_email_token(following) or following in AT_WORDS:
                break
            right.append(following)

        if not left or not right:
            continue

        candidate = _assemble(left) + "@" + _assemble(right)
        candidate = normalize_email(candidate).strip(".")
        if _VALID_EMAIL_RE.fullmatch(candidate):
            return candidate
    return None


def _assemble(tokens: list[str]) -> str:
    return "".join(SEPARATOR_WORDS.get(token, token) for token in tokens)


def compare_emails(observed: str, expected: str) -> bool:
    return normalize_email(observed) == normalize_email(expected)
