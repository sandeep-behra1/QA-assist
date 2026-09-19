"""Lead, call and transcript data access."""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.models import Call, Lead, Transcript, TranscriptSegment


def get_lead(db: Session, lead_id: int) -> Lead | None:
    return db.get(Lead, lead_id)


def list_leads(
    db: Session,
    *,
    retailer_id: int | None = None,
    vertical_id: int | None = None,
    agent_id: int | None = None,
    team_leader_id: int | None = None,
    campaign: str | None = None,
    status: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    limit: int = 200,
    offset: int = 0,
) -> list[Lead]:
    stmt = select(Lead).order_by(Lead.call_datetime.desc())
    if retailer_id is not None:
        stmt = stmt.where(Lead.retailer_id == retailer_id)
    if vertical_id is not None:
        stmt = stmt.where(Lead.vertical_id == vertical_id)
    if agent_id is not None:
        stmt = stmt.where(Lead.agent_id == agent_id)
    if team_leader_id is not None:
        stmt = stmt.where(Lead.team_leader_id == team_leader_id)
    if campaign:
        stmt = stmt.where(Lead.campaign == campaign)
    if status:
        stmt = stmt.where(Lead.status == status)
    if date_from:
        stmt = stmt.where(Lead.call_datetime >= datetime.combine(date_from, datetime.min.time()))
    if date_to:
        stmt = stmt.where(Lead.call_datetime <= datetime.combine(date_to, datetime.max.time()))
    return list(db.scalars(stmt.limit(limit).offset(offset)))


def count_leads(db: Session) -> int:
    return db.scalar(select(func.count(Lead.id))) or 0


def create_lead(db: Session, lead: Lead) -> Lead:
    db.add(lead)
    db.flush()
    return lead


def get_call(db: Session, call_id: int) -> Call | None:
    return db.get(Call, call_id)


def get_or_create_call(db: Session, lead_id: int) -> Call:
    call = db.scalars(select(Call).where(Call.lead_id == lead_id).order_by(Call.id)).first()
    if call is None:
        call = Call(lead_id=lead_id)
        db.add(call)
        db.flush()
    return call


def latest_transcript(db: Session, lead_id: int) -> Transcript | None:
    stmt = (
        select(Transcript)
        .where(Transcript.lead_id == lead_id)
        .order_by(Transcript.id.desc())
        .options(selectinload(Transcript.segments))
    )
    return db.scalars(stmt).first()


def get_transcript(db: Session, transcript_id: int) -> Transcript | None:
    stmt = (
        select(Transcript)
        .where(Transcript.id == transcript_id)
        .options(selectinload(Transcript.segments))
    )
    return db.scalars(stmt).first()


def segments_for_transcript(db: Session, transcript_id: int) -> list[TranscriptSegment]:
    stmt = (
        select(TranscriptSegment)
        .where(TranscriptSegment.transcript_id == transcript_id)
        .order_by(TranscriptSegment.segment_id)
    )
    return list(db.scalars(stmt))
