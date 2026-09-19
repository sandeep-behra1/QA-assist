from __future__ import annotations

from datetime import date

from pydantic import BaseModel, ConfigDict, Field


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class VerticalOut(ORMModel):
    id: int
    code: str
    name: str
    active: bool


class VerticalCreate(BaseModel):
    code: str = Field(min_length=2, max_length=50)
    name: str = Field(min_length=2, max_length=120)
    active: bool = True


class RetailerOut(ORMModel):
    id: int
    code: str
    name: str
    active: bool


class RetailerCreate(BaseModel):
    code: str = Field(min_length=2, max_length=50)
    name: str = Field(min_length=2, max_length=160)
    active: bool = True
    vertical_ids: list[int] = []


class RetailerVerticalOut(ORMModel):
    id: int
    retailer_id: int
    vertical_id: int
    active: bool


class RetailerVerticalCreate(BaseModel):
    retailer_id: int
    vertical_id: int


class PlanOut(ORMModel):
    id: int
    retailer_id: int
    vertical_id: int
    code: str
    name: str
    description: str
    active: bool
    attributes: dict


class PlanCreate(BaseModel):
    retailer_id: int
    vertical_id: int
    code: str = Field(min_length=2, max_length=60)
    name: str = Field(min_length=2, max_length=160)
    description: str = ""
    attributes: dict = {}


class RateCardOut(ORMModel):
    id: int
    plan_id: int
    effective_from: date
    effective_to: date | None
    currency: str
    unit: str
    peak_rate: float | None
    off_peak_rate: float | None
    shoulder_rate: float | None
    daily_supply_charge: float | None
    discount_percent: float | None
    attributes: dict


class RateCardCreate(BaseModel):
    plan_id: int
    effective_from: date
    effective_to: date | None = None
    currency: str = "AUD"
    unit: str = "c/kWh"
    peak_rate: float | None = None
    off_peak_rate: float | None = None
    shoulder_rate: float | None = None
    daily_supply_charge: float | None = None
    discount_percent: float | None = None
    attributes: dict = {}


class AgentOut(ORMModel):
    id: int
    name: str
    team_leader_id: int | None
    site: str | None
    active: bool


class TeamLeaderOut(ORMModel):
    id: int
    name: str
    active: bool


class CampaignOut(ORMModel):
    id: int
    code: str
    name: str


class SiteOut(ORMModel):
    id: int
    code: str
    name: str
