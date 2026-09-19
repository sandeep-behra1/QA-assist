"""Candidate location: the only sanctioned way to search a transcript.

Checks never scan the transcript themselves. Routing every search through
here is what makes "did the evaluator look at the whole relevant scope?"
answerable by inspection -- which is the precondition for allowing an
absence-based FAIL at all.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.core.enums import EvidenceSource, Speaker
from app.models import TranscriptSegment


@dataclass(frozen=True)
class LocatedScope:
    """What was searched, and what looked promising inside it."""

    scope: list[TranscriptSegment]
    candidates: list[TranscriptSegment]
    keywords: list[str]

    @property
    def scope_size(self) -> int:
        return len(self.scope)


_SPEAKER_BY_SOURCE = {
    EvidenceSource.AGENT_TRANSCRIPT.value: Speaker.AGENT.value,
    EvidenceSource.CUSTOMER_TRANSCRIPT.value: Speaker.CUSTOMER.value,
}


def build_scope(segments: list[TranscriptSegment], evidence_source: str) -> list[TranscriptSegment]:
    """All segments a check is permitted to consider."""
    required_speaker = _SPEAKER_BY_SOURCE.get(evidence_source)
    if required_speaker is None:
        return list(segments)
    return [s for s in segments if s.speaker == required_speaker]


def locate(
    segments: list[TranscriptSegment],
    evidence_source: str,
    keywords: list[str] | None = None,
) -> LocatedScope:
    """Narrow a transcript to plausible evidence for a check.

    Keywords are a pre-filter for precision only. When none are configured,
    every in-scope segment is a candidate, so a check is never silently
    prevented from finding its evidence.
    """
    scope = build_scope(segments, evidence_source)
    cleaned = [k.lower() for k in (keywords or []) if k and k.strip()]
    if not cleaned:
        return LocatedScope(scope=scope, candidates=list(scope), keywords=[])

    candidates = [s for s in scope if any(k in s.text.lower() for k in cleaned)]
    return LocatedScope(scope=scope, candidates=candidates, keywords=cleaned)
