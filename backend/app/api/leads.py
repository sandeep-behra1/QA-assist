"""Lead endpoints: CRUD, transcript/audio attachment, scoring, audio streaming."""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, UploadFile
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.api.mappers import lead_detail, lead_summary, scoring_run_out
from app.db.session import get_db
from app.repositories import leads as leads_repo
from app.repositories import scoring as scoring_repo
from app.schemas.audit import AuditEventOut
from app.schemas.lead import LeadCreate, LeadDetail, LeadSummary, LeadUpdate
from app.schemas.scoring import ScoringRunOut, ScoringRunSummary
from app.schemas.transcript import TranscriptOut, TranscriptUpload
from app.services.ingestion import (
    TranscriptValidationError,
    UnsupportedAudioError,
    parse_canonical_json,
    parse_pasted_text,
    store_audio,
    store_transcript,
)
from app.services.leads import (
    LeadNotFoundError,
    LeadValidationError,
    create_lead,
    update_lead,
    validate_lead_for_scoring,
)
from app.services.rules.resolver import NoApplicableChecklistError
from app.services.scoring.engine import TranscriptRequiredError, score_lead
from app.services.storage import FileNotFoundInStorage, get_file_storage

router = APIRouter(prefix="/leads", tags=["leads"])

_AUDIO_CHUNK = 256 * 1024


def _get_lead_or_404(db: Session, lead_id: int):
    lead = leads_repo.get_lead(db, lead_id)
    if lead is None:
        raise HTTPException(status_code=404, detail=f"Lead {lead_id} was not found.")
    return lead


@router.get("", response_model=list[LeadSummary])
def list_leads(
    db: Session = Depends(get_db),
    retailer_id: int | None = None,
    vertical_id: int | None = None,
    agent_id: int | None = None,
    team_leader_id: int | None = None,
    campaign: str | None = None,
    status: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    limit: int = Query(default=200, le=500),
    offset: int = 0,
) -> list[LeadSummary]:
    leads = leads_repo.list_leads(
        db,
        retailer_id=retailer_id,
        vertical_id=vertical_id,
        agent_id=agent_id,
        team_leader_id=team_leader_id,
        campaign=campaign,
        status=status,
        date_from=date_from,
        date_to=date_to,
        limit=limit,
        offset=offset,
    )
    runs = scoring_repo.latest_runs_for_leads(db, [lead.id for lead in leads])
    summaries = []
    for lead in leads:
        transcript = leads_repo.latest_transcript(db, lead.id)
        call = lead.calls[0] if lead.calls else None
        summaries.append(
            lead_summary(
                lead,
                runs.get(lead.id),
                has_transcript=bool(transcript and transcript.segments),
                has_audio=bool(call and call.audio_storage_key),
            )
        )
    return summaries


@router.post("", response_model=LeadDetail, status_code=201)
def create(payload: LeadCreate, db: Session = Depends(get_db)) -> LeadDetail:
    try:
        lead = create_lead(db, payload.model_dump(), actor="ui")
    except LeadValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return lead_detail(db, lead, None)


@router.get("/{lead_id}", response_model=LeadDetail)
def get_lead(lead_id: int, db: Session = Depends(get_db)) -> LeadDetail:
    lead = _get_lead_or_404(db, lead_id)
    return lead_detail(db, lead, scoring_repo.latest_run(db, lead_id))


@router.patch("/{lead_id}", response_model=LeadDetail)
def patch_lead(lead_id: int, payload: LeadUpdate, db: Session = Depends(get_db)) -> LeadDetail:
    try:
        lead = update_lead(db, lead_id, payload.model_dump(exclude_unset=True), actor="ui")
    except LeadNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except LeadValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return lead_detail(db, lead, scoring_repo.latest_run(db, lead_id))


@router.get("/{lead_id}/validate")
def validate(lead_id: int, db: Session = Depends(get_db)) -> dict:
    try:
        problems = validate_lead_for_scoring(db, lead_id)
    except LeadNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"lead_id": lead_id, "ready_to_score": not problems, "problems": problems}


@router.get("/{lead_id}/transcript", response_model=TranscriptOut)
def get_transcript(lead_id: int, db: Session = Depends(get_db)) -> TranscriptOut:
    _get_lead_or_404(db, lead_id)
    transcript = leads_repo.latest_transcript(db, lead_id)
    if transcript is None:
        raise HTTPException(status_code=404, detail=f"Lead {lead_id} has no transcript.")
    return TranscriptOut.model_validate(transcript)


@router.post("/{lead_id}/transcript", response_model=TranscriptOut, status_code=201)
def upload_transcript(
    lead_id: int, payload: TranscriptUpload, db: Session = Depends(get_db)
) -> TranscriptOut:
    lead = _get_lead_or_404(db, lead_id)
    call = lead.calls[0] if lead.calls else None

    try:
        if payload.payload is not None:
            segments, metadata = parse_canonical_json(payload.payload)
        else:
            segments, metadata = parse_pasted_text(payload.pasted_text or ""), {}
    except TranscriptValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    transcript = store_transcript(
        db,
        lead_id=lead_id,
        segments=segments,
        source=payload.source.value,
        language=payload.language,
        call_id=call.id if call else None,
        provider_metadata=metadata,
        actor="ui",
    )
    db.commit()
    db.refresh(transcript)
    return TranscriptOut.model_validate(transcript)


@router.post("/{lead_id}/audio", status_code=201)
async def upload_audio(
    lead_id: int, file: UploadFile = File(...), db: Session = Depends(get_db)
) -> dict:
    _get_lead_or_404(db, lead_id)
    try:
        stored = store_audio(
            db,
            lead_id=lead_id,
            fileobj=file.file,
            filename=file.filename or "recording.wav",
            content_type=file.content_type,
            actor="ui",
        )
    except UnsupportedAudioError as exc:
        raise HTTPException(status_code=415, detail=str(exc)) from exc
    db.commit()
    return {
        "call_id": stored.call.id,
        "size_bytes": stored.size_bytes,
        "filename": stored.call.audio_filename,
        "transcription_status": stored.call.transcription_status,
    }


@router.get("/{lead_id}/audio")
def stream_audio(lead_id: int, request: Request, db: Session = Depends(get_db)):
    """Stream call audio with HTTP Range support.

    Range handling is what lets the reviewer's player seek straight to a
    piece of evidence instead of downloading the whole recording first.
    """
    lead = _get_lead_or_404(db, lead_id)
    call = lead.calls[0] if lead.calls else None
    if call is None or not call.audio_storage_key:
        raise HTTPException(status_code=404, detail=f"Lead {lead_id} has no audio recording.")

    storage = get_file_storage()
    try:
        total = storage.size(call.audio_storage_key)
    except FileNotFoundInStorage as exc:
        raise HTTPException(status_code=404, detail="Audio file is missing from storage.") from exc

    media_type = call.audio_content_type or "application/octet-stream"
    range_header = request.headers.get("range")
    start, end = 0, total - 1
    status_code = 200
    headers = {"accept-ranges": "bytes", "content-type": media_type}

    if range_header and range_header.startswith("bytes="):
        raw = range_header.removeprefix("bytes=").split("-", 1)
        try:
            start = int(raw[0]) if raw[0] else 0
            if len(raw) > 1 and raw[1]:
                end = min(int(raw[1]), total - 1)
        except ValueError:
            raise HTTPException(status_code=416, detail="Malformed Range header.") from None
        if start > end or start >= total:
            raise HTTPException(status_code=416, detail="Requested range is not satisfiable.")
        status_code = 206
        headers["content-range"] = f"bytes {start}-{end}/{total}"

    headers["content-length"] = str(end - start + 1)

    def iterator():
        with storage.open(call.audio_storage_key) as handle:
            handle.seek(start)
            remaining = end - start + 1
            while remaining > 0:
                chunk = handle.read(min(_AUDIO_CHUNK, remaining))
                if not chunk:
                    break
                remaining -= len(chunk)
                yield chunk

    return StreamingResponse(
        iterator(), status_code=status_code, headers=headers, media_type=media_type
    )


@router.post("/{lead_id}/score", response_model=ScoringRunOut, status_code=201)
def score(lead_id: int, db: Session = Depends(get_db)) -> ScoringRunOut:
    _get_lead_or_404(db, lead_id)
    try:
        run = score_lead(db, lead_id, actor="ui")
    except TranscriptRequiredError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except NoApplicableChecklistError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return scoring_run_out(scoring_repo.get_run(db, run.id))


@router.get("/{lead_id}/scoring-runs", response_model=list[ScoringRunSummary])
def list_runs(lead_id: int, db: Session = Depends(get_db)) -> list[ScoringRunSummary]:
    _get_lead_or_404(db, lead_id)
    return [ScoringRunSummary.model_validate(run) for run in scoring_repo.runs_for_lead(db, lead_id)]


@router.get("/{lead_id}/scoring-runs/latest", response_model=ScoringRunOut)
def latest_run(lead_id: int, db: Session = Depends(get_db)) -> ScoringRunOut:
    _get_lead_or_404(db, lead_id)
    run = scoring_repo.latest_run(db, lead_id)
    if run is None:
        raise HTTPException(status_code=404, detail=f"Lead {lead_id} has not been scored yet.")
    return scoring_run_out(run)


@router.get("/{lead_id}/audit-events", response_model=list[AuditEventOut])
def lead_audit(lead_id: int, db: Session = Depends(get_db)) -> list[AuditEventOut]:
    _get_lead_or_404(db, lead_id)
    events = scoring_repo.list_audit_events(db, lead_id=lead_id, limit=200)
    return [AuditEventOut.model_validate(event) for event in events]
