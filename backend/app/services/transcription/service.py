"""Transcription orchestration: create a job, then attach it to a lead.

    audio --> [provider] --> canonical segments --> TranscriptionJob (staged)
                                                        |
                              lead created / chosen --> attach --> Transcript + Call audio

Redaction runs here, once, on the way in: the staged job, the API preview and
the eventual Transcript never contain card numbers or one-time codes.
"""

from __future__ import annotations

import io
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.enums import (
    AuditEventType,
    TranscriptionJobStatus,
    TranscriptionStatus,
    TranscriptSource,
)
from app.models import Call, TranscriptionJob
from app.repositories import leads as leads_repo
from app.services.audit import record_event
from app.services.ingestion.audio import ALLOWED_EXTENSIONS, UnsupportedAudioError, _extension
from app.services.ingestion.transcript import ParsedSegment, normalize_speaker, store_transcript
from app.services.normalization import redact_sensitive_data
from app.services.storage import get_file_storage
from app.services.transcription.providers import (
    EmbeddedTranscriptProvider,
    GroqWhisperProvider,
    RawSegment,
    TranscriptionError,
    TranscriptionProvider,
)


class UploadTooLargeError(ValueError):
    pass


class JobNotFoundError(LookupError):
    pass


class JobNotAttachableError(ValueError):
    pass


class UnknownProviderError(ValueError):
    pass


def build_provider(key: str, settings: Settings) -> TranscriptionProvider:
    if key == "groq":
        return GroqWhisperProvider(settings)
    if key == "embedded":
        return EmbeddedTranscriptProvider()
    raise UnknownProviderError(f"Unknown transcription provider '{key}'. Use 'groq' or 'embedded'.")


def list_providers(settings: Settings | None = None) -> list[dict]:
    settings = settings or get_settings()
    groq = GroqWhisperProvider(settings)
    embedded = EmbeddedTranscriptProvider()
    return [
        {
            "key": groq.key,
            "label": groq.label,
            "model": settings.groq_stt_model,
            "ready": groq.ready(),
            "note": None if groq.ready() else "Set GROQ_API_KEY in backend/.env to enable.",
        },
        {
            "key": embedded.key,
            "label": embedded.label,
            "model": None,
            "ready": True,
            "note": "Works only with recordings made by the demo generator.",
        },
    ]


def default_provider_key(settings: Settings | None = None) -> str:
    settings = settings or get_settings()
    return "groq" if settings.stt_ready else "embedded"


def _canonicalise(raw: list[RawSegment]) -> list[dict]:
    ordered = sorted(raw, key=lambda s: (s.start, s.end))
    segments = []
    for number, item in enumerate(ordered, start=1):
        segments.append(
            {
                "segment_id": number,
                "speaker": normalize_speaker(item.speaker or "UNKNOWN"),
                "start_time": round(item.start, 2),
                "end_time": round(max(item.end, item.start), 2),
                "text": redact_sensitive_data(item.text),
                "asr_confidence": item.confidence,
            }
        )
    return segments


def create_job(
    db: Session,
    *,
    data: bytes,
    filename: str,
    content_type: str | None,
    provider_key: str | None = None,
    actor: str = "system",
    settings: Settings | None = None,
) -> TranscriptionJob:
    settings = settings or get_settings()

    extension = _extension(filename)
    if extension not in ALLOWED_EXTENSIONS:
        raise UnsupportedAudioError(
            f"Unsupported audio type '{extension or filename}'. Allowed: {', '.join(sorted(ALLOWED_EXTENSIONS))}."
        )
    if len(data) > settings.max_upload_bytes:
        raise UploadTooLargeError(
            f"Audio is {len(data) / 1_048_576:.1f} MB; the limit is {settings.max_upload_bytes / 1_048_576:.0f} MB."
        )

    provider = build_provider(provider_key or default_provider_key(settings), settings)

    job = TranscriptionJob(
        provider=provider.key,
        audio_filename=filename,
        audio_content_type=content_type,
        audio_size_bytes=len(data),
        audio_storage_key="",
    )
    job.audio_storage_key = f"staging/{job.id}{extension}"
    get_file_storage().save(job.audio_storage_key, io.BytesIO(data), content_type)

    try:
        result = provider.transcribe(data, filename, content_type)
        segments = _canonicalise(result.segments)
        if not segments:
            raise TranscriptionError("No speech was detected in this recording.")
    except TranscriptionError as exc:
        job.status = TranscriptionJobStatus.FAILED.value
        job.error = str(exc)[:1000]
        db.add(job)
        db.flush()
        record_event(
            db,
            event_type=AuditEventType.TRANSCRIPTION_FAILED,
            entity_type="transcription_job",
            entity_id=job.id,
            actor=actor,
            details={"provider": provider.key, "filename": filename, "error": job.error},
        )
        db.commit()
        return job

    job.status = TranscriptionJobStatus.COMPLETED.value
    job.model = result.model
    job.language = result.language
    job.diarization = result.diarization.value
    job.duration_seconds = result.duration_seconds
    job.channels = result.channels
    job.latency_ms = result.latency_ms
    job.warnings = list(result.warnings)
    job.segments = segments
    db.add(job)
    db.flush()
    record_event(
        db,
        event_type=AuditEventType.TRANSCRIPTION_COMPLETED,
        entity_type="transcription_job",
        entity_id=job.id,
        actor=actor,
        details={
            "provider": provider.key,
            "model": result.model,
            "diarization": result.diarization.value,
            "segments": len(segments),
            "latency_ms": result.latency_ms,
            "filename": filename,
            "warnings": len(result.warnings),
        },
    )
    db.commit()
    db.refresh(job)
    return job


def get_job(db: Session, job_id: str) -> TranscriptionJob:
    job = db.get(TranscriptionJob, job_id)
    if job is None:
        raise JobNotFoundError(f"Transcription job {job_id} was not found.")
    return job


def attach_job_to_lead(db: Session, job_id: str, lead_id: int, actor: str = "system"):
    """Give a lead the job's audio and its transcript, then mark it available."""
    job = get_job(db, job_id)
    if job.status != TranscriptionJobStatus.COMPLETED.value:
        raise JobNotAttachableError("Only a completed transcription can be attached to a sale.")
    if job.lead_id is not None and job.lead_id != lead_id:
        raise JobNotAttachableError(f"This transcription is already attached to lead {job.lead_id}.")

    lead = leads_repo.get_lead(db, lead_id)
    if lead is None:
        raise JobNotAttachableError(f"Lead {lead_id} was not found.")

    storage = get_file_storage()
    call = leads_repo.get_or_create_call(db, lead_id)
    extension = _extension(job.audio_filename)
    lead_key = f"leads/{lead_id}/calls/{call.id}{extension}"
    with storage.open(job.audio_storage_key) as staged:
        storage.save(lead_key, staged, job.audio_content_type)

    call.audio_storage_key = lead_key
    call.audio_filename = job.audio_filename
    call.audio_content_type = job.audio_content_type or "application/octet-stream"
    call.audio_size_bytes = job.audio_size_bytes
    if job.duration_seconds is not None:
        call.duration_seconds = job.duration_seconds
    call.transcription_status = TranscriptionStatus.AVAILABLE.value

    record_event(
        db,
        event_type=AuditEventType.AUDIO_UPLOADED,
        entity_type="call",
        entity_id=call.id,
        actor=actor,
        lead_id=lead_id,
        details={"filename": job.audio_filename, "size_bytes": job.audio_size_bytes, "via": "transcription_job"},
    )

    parsed = [
        ParsedSegment(
            segment_id=s["segment_id"],
            speaker=s["speaker"],
            start_time=s["start_time"],
            end_time=s["end_time"],
            text=s["text"],
            asr_confidence=s["asr_confidence"],
        )
        for s in job.segments
    ]
    transcript = store_transcript(
        db,
        lead_id=lead_id,
        segments=parsed,
        source=(
            TranscriptSource.EMBEDDED_DEMO.value
            if job.provider == "embedded"
            else TranscriptSource.WHISPER.value
        ),
        language=job.language,
        call_id=call.id,
        provider_metadata={
            "transcription_job_id": job.id,
            "provider": job.provider,
            "model": job.model,
            "diarization": job.diarization,
            "latency_ms": job.latency_ms,
            "warnings": job.warnings,
        },
        actor=actor,
    )

    job.lead_id = lead_id
    job.attached_at = datetime.now(UTC)
    staged_key = job.audio_storage_key
    db.commit()
    db.refresh(transcript)
    if staged_key != lead_key:
        storage.delete(staged_key)
    return transcript


def transcribe_lead_audio(
    db: Session,
    lead_id: int,
    provider_key: str | None = None,
    actor: str = "system",
    settings: Settings | None = None,
):
    """The "Transcribe Audio" action for a sale that already has a recording."""
    lead = leads_repo.get_lead(db, lead_id)
    if lead is None:
        raise JobNotAttachableError(f"Lead {lead_id} was not found.")
    call = lead.calls[0] if lead.calls else None
    if call is None or not call.audio_storage_key:
        raise JobNotAttachableError(f"Lead {lead_id} has no audio recording to transcribe.")

    call.transcription_status = TranscriptionStatus.PENDING.value
    db.commit()

    with get_file_storage().open(call.audio_storage_key) as handle:
        data = handle.read()
    job = create_job(
        db,
        data=data,
        filename=call.audio_filename or "recording.wav",
        content_type=call.audio_content_type,
        provider_key=provider_key,
        actor=actor,
        settings=settings,
    )
    if job.status != TranscriptionJobStatus.COMPLETED.value:
        call = db.get(Call, call.id)
        call.transcription_status = TranscriptionStatus.FAILED.value
        db.commit()
        return job, None
    return job, attach_job_to_lead(db, job.id, lead_id, actor)


__all__ = [
    "JobNotAttachableError",
    "JobNotFoundError",
    "UnknownProviderError",
    "UploadTooLargeError",
    "attach_job_to_lead",
    "build_provider",
    "create_job",
    "default_provider_key",
    "get_job",
    "list_providers",
    "transcribe_lead_audio",
]
