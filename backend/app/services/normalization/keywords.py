"""Keyword matching used to find candidate evidence.

Plain substring search is a false-pass hazard in two ways:
  * "peak rate" matches inside "off-peak rate", so an off-peak figure could be
    read as the peak rate;
  * short keywords match inside longer words ("nmi" in "administration").

So keywords match on word boundaries, and a keyword starting with "peak" never
matches when it is really part of "off-peak" / "off peak".
"""

from __future__ import annotations

import re
from functools import lru_cache

_OFF_PREFIX_RE = re.compile(r"off[\s\-]*$")


@lru_cache(maxsize=512)
def _compile(keyword: str) -> re.Pattern[str]:
    return re.compile(rf"(?<![A-Za-z0-9]){re.escape(keyword)}(?![A-Za-z0-9])")


def keyword_positions(text: str, keyword: str) -> list[int]:
    lowered = text.lower()
    key = keyword.lower().strip()
    if not key:
        return []
    positions: list[int] = []
    for match in _compile(key).finditer(lowered):
        if key.startswith("peak") and _OFF_PREFIX_RE.search(lowered[: match.start()]):
            continue
        positions.append(match.start())
    return positions


def contains_keyword(text: str, keyword: str) -> bool:
    return bool(keyword_positions(text, keyword))


def contains_any_keyword(text: str, keywords: list[str]) -> bool:
    return any(contains_keyword(text, keyword) for keyword in keywords)
