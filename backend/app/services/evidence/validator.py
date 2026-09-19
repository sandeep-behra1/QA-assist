"""Evidence validation.

Every evidence reference -- whether produced by a regex or by a language
model -- must resolve to a transcript segment that actually exists. This is
the concrete control that stops a hallucinated citation from ever being
persisted or shown to a reviewer.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.models import TranscriptSegment


@dataclass(frozen=True)
class ValidationOutcome:
    valid_segments: list[TranscriptSegment]
    invalid_ids: list[int]

    @property
    def had_invalid_references(self) -> bool:
        return bool(self.invalid_ids)


def validate_segment_ids(
    segments: list[TranscriptSegment], segment_ids: list[int]
) -> ValidationOutcome:
    """Resolve claimed segment ids against the real transcript.

    Ids that do not exist are discarded and reported, never silently
    dropped: a caller that ends up with no valid evidence must treat the
    result as unproven rather than assume the citation was close enough.
    """
    by_id = {segment.segment_id: segment for segment in segments}
    valid: list[TranscriptSegment] = []
    invalid: list[int] = []
    seen: set[int] = set()

    for raw_id in segment_ids:
        try:
            segment_id = int(raw_id)
        except (TypeError, ValueError):
            invalid.append(raw_id)
            continue
        if segment_id in seen:
            continue
        seen.add(segment_id)
        segment = by_id.get(segment_id)
        if segment is None:
            invalid.append(segment_id)
        else:
            valid.append(segment)

    valid.sort(key=lambda s: s.segment_id)
    return ValidationOutcome(valid_segments=valid, invalid_ids=invalid)
