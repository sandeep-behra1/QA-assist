"""Transcript ingestion: the boundary between "some provider" and the engine.

Anything that can produce the canonical shape -- a pasted transcript, a JSON
upload, CIMET's own pipeline, or a future Whisper/Deepgram call -- enters
here. Redaction happens once, at this boundary, so no card number can reach
scoring, an LLM prompt, the API or the UI.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.core.enums import AuditEventType, Speaker, TranscriptSource
from app.models import Transcript, TranscriptSegment
from app.services.audit import record_event
from app.services.normalization import redact_sensitive_data


class TranscriptValidationError(ValueError):
    pass


@dataclass(frozen=True)
class ParsedSegment:
    segment_id: int
    speaker: str
    start_time: float
    end_time: float
    text: str
    asr_confidence: float | None


_SPEAKER_ALIASES = {
    "AGENT": Speaker.AGENT.value,
    "REP": Speaker.AGENT.value,
    "SALES": Speaker.AGENT.value,
    "CUSTOMER": Speaker.CUSTOMER.value,
    "CLIENT": Speaker.CUSTOMER.value,
    "CALLER": Speaker.CUSTOMER.value,
}

_PASTED_LINE_RE = re.compile(
    r"^\s*(?:\[?(?P<start>\d+(?:\.\d+)?)\s*(?:-|to)?\s*(?P<end>\d+(?:\.\d+)?)?\]?\s+)?"
    r"(?P<speaker>[A-Za-z ]{2,20})\s*:\s*(?P<text>.+)$"
)


def normalize_speaker(raw: str) -> str:
    return _SPEAKER_ALIASES.get(str(raw).strip().upper(), Speaker.UNKNOWN.value)


def parse_canonical_json(payload: dict | str) -> tuple[list[ParsedSegment], dict]:
    """Parse the canonical transcript JSON contract."""
    if isinstance(payload, str):
        try:
            payload = json.loads(payload)
        except json.JSONDecodeError as exc:
            raise TranscriptValidationError(f"Transcript is not valid JSON: {exc}") from exc

    if not isinstance(payload, dict):
        raise TranscriptValidationError("Transcript payload must be a JSON object.")

    raw_segments = payload.get("segments")
    if not isinstance(raw_segments, list) or not raw_segments:
        raise TranscriptValidationError("Transcript must contain a non-empty 'segments' array.")

    segments: list[ParsedSegment] = []
    for index, raw in enumerate(raw_segments, start=1):
        if not isinstance(raw, dict):
            raise TranscriptValidationError(f"Segment {index} is not an object.")
        text = str(raw.get("text", "")).strip()
        if not text:
            raise TranscriptValidationError(f"Segment {index} has no text.")
        try:
            start_time = float(raw.get("start_time", 0.0))
            end_time = float(raw.get("end_time", start_time))
        except (TypeError, ValueError) as exc:
            raise TranscriptValidationError(f"Segment {index} has non-numeric timings.") from exc
        if end_time < start_time:
            raise TranscriptValidationError(f"Segment {index} ends before it starts.")

        confidence = raw.get("asr_confidence")
        segments.append(
            ParsedSegment(
                segment_id=int(raw.get("segment_id", index)),
                speaker=normalize_speaker(raw.get("speaker", "UNKNOWN")),
                start_time=start_time,
                end_time=end_time,
                text=text,
                asr_confidence=float(confidence) if confidence is not None else None,
            )
        )

    _assert_unique_segment_ids(segments)
    metadata = {
        key: value
        for key, value in payload.items()
        if key in {"transcript_id", "call_id", "source", "language", "provider"}
    }
    return segments, metadata


def parse_pasted_text(text: str) -> list[ParsedSegment]:
    """Parse a pasted "SPEAKER: text" transcript.

    Timings are synthesised (2s per line) when absent. They are only used for
    ordering and playback hints -- behaviour checks that depend on real
    timings should run against an uploaded canonical transcript instead.
    """
    segments: list[ParsedSegment] = []
    cursor = 0.0
    for line in text.splitlines():
        if not line.strip():
            continue
        match = _PASTED_LINE_RE.match(line)
        if not match:
            continue
        start = float(match.group("start")) if match.group("start") else cursor
        end = float(match.group("end")) if match.group("end") else start + 2.0
        segments.append(
            ParsedSegment(
                segment_id=len(segments) + 1,
                speaker=normalize_speaker(match.group("speaker")),
                start_time=start,
                end_time=end,
                text=match.group("text").strip(),
                asr_confidence=None,
            )
        )
        cursor = end

    if not segments:
        raise TranscriptValidationError(
            "No transcript lines were recognised. Use 'AGENT: what they said' per line."
        )
    return segments


def _assert_unique_segment_ids(segments: list[ParsedSegment]) -> None:
    seen: set[int] = set()
    for segment in segments:
        if segment.segment_id in seen:
            raise TranscriptValidationError(f"Duplicate segment_id {segment.segment_id}.")
        seen.add(segment.segment_id)


def store_transcript(
    db: Session,
    *,
    lead_id: int,
    segments: list[ParsedSegment],
    source: str = TranscriptSource.MANUAL_UPLOAD.value,
    language: str = "en-AU",
    call_id: int | None = None,
    provider_metadata: dict | None = None,
    actor: str = "system",
) -> Transcript:
    transcript = Transcript(
        lead_id=lead_id,
        call_id=call_id,
        source=source,
        language=language,
        provider_metadata=provider_metadata or {},
    )
    db.add(transcript)
    db.flush()

    for segment in segments:
        db.add(
            TranscriptSegment(
                transcript_id=transcript.id,
                segment_id=segment.segment_id,
                speaker=segment.speaker,
                start_time=segment.start_time,
                end_time=segment.end_time,
                # Redact once, here, so nothing downstream can leak it.
                text=redact_sensitive_data(segment.text),
                asr_confidence=segment.asr_confidence,
            )
        )
    db.flush()

    record_event(
        db,
        event_type=AuditEventType.TRANSCRIPT_UPLOADED,
        entity_type="transcript",
        entity_id=transcript.id,
        actor=actor,
        lead_id=lead_id,
        details={"source": source, "segment_count": len(segments), "language": language},
    )
    return transcript
