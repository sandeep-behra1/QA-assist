"""Catalog data access: verticals, retailers, plans, rate cards, org units."""

from __future__ import annotations

from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    Agent,
    Campaign,
    Plan,
    RateCard,
    Retailer,
    RetailerVertical,
    Site,
    TeamLeader,
    Vertical,
)


def list_verticals(db: Session, active_only: bool = False) -> list[Vertical]:
    stmt = select(Vertical).order_by(Vertical.name)
    if active_only:
        stmt = stmt.where(Vertical.active.is_(True))
    return list(db.scalars(stmt))


def get_vertical(db: Session, vertical_id: int) -> Vertical | None:
    return db.get(Vertical, vertical_id)


def get_vertical_by_code(db: Session, code: str) -> Vertical | None:
    return db.scalar(select(Vertical).where(Vertical.code == code))


def list_retailers(db: Session, vertical_id: int | None = None) -> list[Retailer]:
    stmt = select(Retailer).order_by(Retailer.name)
    if vertical_id is not None:
        stmt = stmt.join(RetailerVertical).where(RetailerVertical.vertical_id == vertical_id)
    return list(db.scalars(stmt))


def get_retailer(db: Session, retailer_id: int) -> Retailer | None:
    return db.get(Retailer, retailer_id)


def list_retailer_verticals(db: Session, retailer_id: int | None = None) -> list[RetailerVertical]:
    stmt = select(RetailerVertical)
    if retailer_id is not None:
        stmt = stmt.where(RetailerVertical.retailer_id == retailer_id)
    return list(db.scalars(stmt))


def list_plans(db: Session, retailer_id: int | None = None, vertical_id: int | None = None) -> list[Plan]:
    stmt = select(Plan).order_by(Plan.name)
    if retailer_id is not None:
        stmt = stmt.where(Plan.retailer_id == retailer_id)
    if vertical_id is not None:
        stmt = stmt.where(Plan.vertical_id == vertical_id)
    return list(db.scalars(stmt))


def get_plan(db: Session, plan_id: int) -> Plan | None:
    return db.get(Plan, plan_id)


def list_rate_cards(db: Session, plan_id: int | None = None) -> list[RateCard]:
    stmt = select(RateCard).order_by(RateCard.plan_id, RateCard.effective_from)
    if plan_id is not None:
        stmt = stmt.where(RateCard.plan_id == plan_id)
    return list(db.scalars(stmt))


def get_rate_card_for_date(db: Session, plan_id: int, on_date: date) -> RateCard | None:
    """The rate card in force for a plan on a given date.

    Returns None when there is no covering card -- callers must treat that
    as missing authoritative data, never as zero.
    """
    stmt = (
        select(RateCard)
        .where(RateCard.plan_id == plan_id)
        .where(RateCard.effective_from <= on_date)
        .where((RateCard.effective_to.is_(None)) | (RateCard.effective_to >= on_date))
        .order_by(RateCard.effective_from.desc())
    )
    return db.scalars(stmt).first()


def list_agents(db: Session) -> list[Agent]:
    return list(db.scalars(select(Agent).order_by(Agent.name)))


def get_agent(db: Session, agent_id: int) -> Agent | None:
    return db.get(Agent, agent_id)


def list_team_leaders(db: Session) -> list[TeamLeader]:
    return list(db.scalars(select(TeamLeader).order_by(TeamLeader.name)))


def list_campaigns(db: Session) -> list[Campaign]:
    return list(db.scalars(select(Campaign).order_by(Campaign.name)))


def list_sites(db: Session) -> list[Site]:
    return list(db.scalars(select(Site).order_by(Site.name)))
