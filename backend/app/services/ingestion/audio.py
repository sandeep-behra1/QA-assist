"""Audio ingestion.

Audio is stored, associated with a Call, and served back for reviewer
playback. Transcription is deliberately not implemented: the Call carries a
``transcription_status`` so a future "Transcribe Audio" action can move it
NOT_STARTED -> PENDING -> AVAILABLE and write a canonical Transcript,
without any downstream scoring change.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import BinaryIO

from sqlalchemy.orm import Session

from app.core.enums import AuditEventType, TranscriptionStatus
from app.models import Call
from app.repositories import leads as leads_repo
from app.services.audit import record_event
from app.services.storage import get_file_storage

ALLOWED_CONTENT_TYPES = {
    "audio/wav",
    "audio/x-wav",
    "audio/wave",
    "audio/mpeg",
    "audio/mp3",
    "audio/mp4",
    "audio/m4a",
    "audio/x-m4a",
    "audio/aac",
    "audio/ogg",
    "application/octet-stream",
}

ALLOWED_EXTENSIONS = {".wav", ".mp3", ".m4a", ".aac", ".ogg", ".mp4"}


class UnsupportedAudioError(ValueError):
    pass


@dataclass(frozen=True)
class StoredAudio:
    call: Call
    storage_key: str
    size_bytes: int


def _extension(filename: str) -> str:
    _, _, suffix = filename.rpartition(".")
    return f".{suffix.lower()}" if suffix else ""


def store_audio(
    db: Session,
    *,
    lead_id: int,
    fileobj: BinaryIO,
    filename: str,
    content_type: str | None,
    duration_seconds: float | None = None,
    actor: str = "system",
) -> StoredAudio:
    extension = _extension(filename)
    if extension not in ALLOWED_EXTENSIONS:
        raise UnsupportedAudioError(
            f"Unsupported audio type '{extension or filename}'. "
            f"Allowed: {', '.join(sorted(ALLOWED_EXTENSIONS))}."
        )
    if content_type and content_type not in ALLOWED_CONTENT_TYPES:
        raise UnsupportedAudioError(f"Unsupported content type '{content_type}'.")

    call = leads_repo.get_or_create_call(db, lead_id)
    storage = get_file_storage()
    key = f"leads/{lead_id}/calls/{call.id}{extension}"
    stored = storage.save(key, fileobj, content_type)

    call.audio_storage_key = stored.key
    call.audio_filename = filename
    call.audio_content_type = content_type or "application/octet-stream"
    call.audio_size_bytes = stored.size_bytes
    if duration_seconds is not None:
        call.duration_seconds = duration_seconds
    # Audio present but not transcribed: this is the hook a future
    # transcription provider flips to PENDING/AVAILABLE.
    call.transcription_status = TranscriptionStatus.NOT_STARTED.value
    db.flush()

    record_event(
        db,
        event_type=AuditEventType.AUDIO_UPLOADED,
        entity_type="call",
        entity_id=call.id,
        actor=actor,
        lead_id=lead_id,
        details={"filename": filename, "size_bytes": stored.size_bytes, "content_type": content_type},
    )
    return StoredAudio(call=call, storage_key=stored.key, size_bytes=stored.size_bytes)
