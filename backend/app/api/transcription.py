"""Transcription endpoints: audio in, canonical transcript out."""

from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.session import get_db
from app.schemas.transcript import TranscriptOut
from app.schemas.transcription import (
    AttachRequest,
    ProviderOut,
    TranscribeRequest,
    TranscriptionJobOut,
)
from app.services.ingestion.audio import UnsupportedAudioError
from app.services.transcription import service

router = APIRouter(tags=["transcription"])


@router.get("/transcription/providers", response_model=list[ProviderOut])
def providers() -> list[dict]:
    return service.list_providers()


@router.post("/transcription-jobs", response_model=TranscriptionJobOut, status_code=201)
async def create_transcription_job(
    file: UploadFile = File(...),
    provider: str | None = Form(default=None),
    db: Session = Depends(get_db),
):
    """Transcribe an uploaded recording. The job is stored whether or not it succeeds.

    A provider failure is reported in the job (``status=FAILED`` + ``error``)
    rather than as an HTTP error, so the UI can show the reason and offer the
    other provider without losing the uploaded file.
    """
    limit = get_settings().max_upload_bytes
    data = await file.read(limit + 1)
    try:
        return service.create_job(
            db,
            data=data,
            filename=file.filename or "recording.wav",
            content_type=file.content_type,
            provider_key=provider,
            actor="ui",
        )
    except UnsupportedAudioError as exc:
        raise HTTPException(status_code=415, detail=str(exc)) from exc
    except service.UploadTooLargeError as exc:
        raise HTTPException(status_code=413, detail=str(exc)) from exc
    except service.UnknownProviderError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/transcription-jobs/{job_id}", response_model=TranscriptionJobOut)
def get_transcription_job(job_id: str, db: Session = Depends(get_db)):
    try:
        return service.get_job(db, job_id)
    except service.JobNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/transcription-jobs/{job_id}/attach", response_model=TranscriptOut)
def attach_transcription_job(job_id: str, payload: AttachRequest, db: Session = Depends(get_db)):
    """Attach a completed job's audio and transcript to a lead."""
    try:
        return service.attach_job_to_lead(db, job_id, payload.lead_id, actor="ui")
    except service.JobNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except service.JobNotAttachableError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/leads/{lead_id}/transcribe", response_model=TranscriptionJobOut)
def transcribe_existing_audio(
    lead_id: int, payload: TranscribeRequest | None = None, db: Session = Depends(get_db)
):
    """The "Transcribe Audio" button for a sale that already has a recording."""
    try:
        job, _ = service.transcribe_lead_audio(
            db, lead_id, (payload.provider if payload else None), actor="ui"
        )
        return job
    except service.JobNotAttachableError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except service.UnknownProviderError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
