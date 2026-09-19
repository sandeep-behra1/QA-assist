"""Configuration endpoints for verticals, retailers, plans and rate cards."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models import Plan, RateCard, Retailer, RetailerVertical, Vertical
from app.repositories import catalog as catalog_repo
from app.schemas.catalog import (
    AgentOut,
    CampaignOut,
    PlanCreate,
    PlanOut,
    RateCardCreate,
    RateCardOut,
    RetailerCreate,
    RetailerOut,
    RetailerVerticalCreate,
    RetailerVerticalOut,
    SiteOut,
    TeamLeaderOut,
    VerticalCreate,
    VerticalOut,
)

router = APIRouter(tags=["configuration"])


@router.get("/verticals", response_model=list[VerticalOut])
def list_verticals(db: Session = Depends(get_db)) -> list[Vertical]:
    return catalog_repo.list_verticals(db)


@router.post("/verticals", response_model=VerticalOut, status_code=201)
def create_vertical(payload: VerticalCreate, db: Session = Depends(get_db)) -> Vertical:
    vertical = Vertical(**payload.model_dump())
    db.add(vertical)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail=f"Vertical '{payload.code}' already exists.") from exc
    db.refresh(vertical)
    return vertical


@router.get("/retailers", response_model=list[RetailerOut])
def list_retailers(vertical_id: int | None = None, db: Session = Depends(get_db)) -> list[Retailer]:
    return catalog_repo.list_retailers(db, vertical_id=vertical_id)


@router.post("/retailers", response_model=RetailerOut, status_code=201)
def create_retailer(payload: RetailerCreate, db: Session = Depends(get_db)) -> Retailer:
    data = payload.model_dump()
    vertical_ids = data.pop("vertical_ids", [])
    retailer = Retailer(**data)
    db.add(retailer)
    try:
        db.flush()
        for vertical_id in vertical_ids:
            db.add(RetailerVertical(retailer_id=retailer.id, vertical_id=vertical_id))
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail=f"Retailer '{payload.code}' already exists.") from exc
    db.refresh(retailer)
    return retailer


@router.get("/retailers/{retailer_id}", response_model=RetailerOut)
def get_retailer(retailer_id: int, db: Session = Depends(get_db)) -> Retailer:
    retailer = catalog_repo.get_retailer(db, retailer_id)
    if retailer is None:
        raise HTTPException(status_code=404, detail=f"Retailer {retailer_id} was not found.")
    return retailer


@router.get("/retailer-verticals", response_model=list[RetailerVerticalOut])
def list_retailer_verticals(
    retailer_id: int | None = None, db: Session = Depends(get_db)
) -> list[RetailerVertical]:
    return catalog_repo.list_retailer_verticals(db, retailer_id=retailer_id)


@router.post("/retailer-verticals", response_model=RetailerVerticalOut, status_code=201)
def create_retailer_vertical(
    payload: RetailerVerticalCreate, db: Session = Depends(get_db)
) -> RetailerVertical:
    link = RetailerVertical(**payload.model_dump())
    db.add(link)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="That retailer/vertical link already exists.") from exc
    db.refresh(link)
    return link


@router.get("/plans", response_model=list[PlanOut])
def list_plans(
    retailer_id: int | None = None, vertical_id: int | None = None, db: Session = Depends(get_db)
) -> list[Plan]:
    return catalog_repo.list_plans(db, retailer_id=retailer_id, vertical_id=vertical_id)


@router.post("/plans", response_model=PlanOut, status_code=201)
def create_plan(payload: PlanCreate, db: Session = Depends(get_db)) -> Plan:
    plan = Plan(**payload.model_dump())
    db.add(plan)
    db.commit()
    db.refresh(plan)
    return plan


@router.get("/rate-cards", response_model=list[RateCardOut])
def list_rate_cards(plan_id: int | None = None, db: Session = Depends(get_db)) -> list[RateCard]:
    return catalog_repo.list_rate_cards(db, plan_id=plan_id)


@router.post("/rate-cards", response_model=RateCardOut, status_code=201)
def create_rate_card(payload: RateCardCreate, db: Session = Depends(get_db)) -> RateCard:
    rate_card = RateCard(**payload.model_dump())
    db.add(rate_card)
    db.commit()
    db.refresh(rate_card)
    return rate_card


@router.get("/agents", response_model=list[AgentOut])
def list_agents(db: Session = Depends(get_db)):
    return catalog_repo.list_agents(db)


@router.get("/team-leaders", response_model=list[TeamLeaderOut])
def list_team_leaders(db: Session = Depends(get_db)):
    return catalog_repo.list_team_leaders(db)


@router.get("/campaigns", response_model=list[CampaignOut])
def list_campaigns(db: Session = Depends(get_db)):
    return catalog_repo.list_campaigns(db)


@router.get("/sites", response_model=list[SiteOut])
def list_sites(db: Session = Depends(get_db)):
    return catalog_repo.list_sites(db)
