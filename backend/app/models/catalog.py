"""Reference/catalog data: Vertical -> Retailer -> Plan -> RateCard.

This hierarchy is the reason a new retailer, plan or vertical needs no
Python change: everything the scoring engine reads about "who sold what at
which price" comes from these tables.
"""

from datetime import date

from sqlalchemy import (
    Boolean,
    Date,
    Float,
    ForeignKey,
    Integer,
    Sequence,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin
from app.db.types import FlexibleJSON


class Vertical(Base, TimestampMixin):
    __tablename__ = "verticals"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    retailer_links: Mapped[list["RetailerVertical"]] = relationship(
        back_populates="vertical", cascade="all, delete-orphan"
    )


class Retailer(Base, TimestampMixin):
    __tablename__ = "retailers"

    id: Mapped[int] = mapped_column(
        Integer, Sequence("retailer_id_seq", start=101), primary_key=True
    )
    code: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    vertical_links: Mapped[list["RetailerVertical"]] = relationship(
        back_populates="retailer", cascade="all, delete-orphan"
    )
    plans: Mapped[list["Plan"]] = relationship(back_populates="retailer")


class RetailerVertical(Base):
    """Which verticals a retailer actually trades in."""

    __tablename__ = "retailer_verticals"
    __table_args__ = (UniqueConstraint("retailer_id", "vertical_id", name="uq_retailer_vertical"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    retailer_id: Mapped[int] = mapped_column(ForeignKey("retailers.id", ondelete="CASCADE"), nullable=False)
    vertical_id: Mapped[int] = mapped_column(ForeignKey("verticals.id", ondelete="CASCADE"), nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    retailer: Mapped["Retailer"] = relationship(back_populates="vertical_links")
    vertical: Mapped["Vertical"] = relationship(back_populates="retailer_links")


class Plan(Base, TimestampMixin):
    __tablename__ = "plans"

    id: Mapped[int] = mapped_column(Integer, Sequence("plan_id_seq", start=2045), primary_key=True)
    retailer_id: Mapped[int] = mapped_column(ForeignKey("retailers.id"), nullable=False)
    vertical_id: Mapped[int] = mapped_column(ForeignKey("verticals.id"), nullable=False)
    code: Mapped[str] = mapped_column(String(60), nullable=False)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    description: Mapped[str] = mapped_column(String(500), default="", nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    # Vertical-specific plan facts (e.g. contract_length_months, exit_fee).
    attributes: Mapped[dict] = mapped_column(FlexibleJSON, default=dict, nullable=False)

    retailer: Mapped["Retailer"] = relationship(back_populates="plans")
    vertical: Mapped["Vertical"] = relationship()
    rate_cards: Mapped[list["RateCard"]] = relationship(back_populates="plan", cascade="all, delete-orphan")


class RateCard(Base, TimestampMixin):
    """Authoritative pricing for a plan over a date window.

    Rate cards are date-effective for the same reason checklists are: a call
    from August must be scored against August's prices, not today's.
    """

    __tablename__ = "rate_cards"

    id: Mapped[int] = mapped_column(Integer, Sequence("rate_card_id_seq", start=5001), primary_key=True)
    plan_id: Mapped[int] = mapped_column(ForeignKey("plans.id", ondelete="CASCADE"), nullable=False)
    effective_from: Mapped[date] = mapped_column(Date, nullable=False)
    effective_to: Mapped[date | None] = mapped_column(Date, nullable=True)
    currency: Mapped[str] = mapped_column(String(10), default="AUD", nullable=False)
    unit: Mapped[str] = mapped_column(String(20), default="c/kWh", nullable=False)
    peak_rate: Mapped[float | None] = mapped_column(Float, nullable=True)
    off_peak_rate: Mapped[float | None] = mapped_column(Float, nullable=True)
    shoulder_rate: Mapped[float | None] = mapped_column(Float, nullable=True)
    daily_supply_charge: Mapped[float | None] = mapped_column(Float, nullable=True)
    discount_percent: Mapped[float | None] = mapped_column(Float, nullable=True)
    # Anything a future vertical prices differently (e.g. feed_in_tariff,
    # comparison_rate, monthly_fee) lands here without a migration.
    attributes: Mapped[dict] = mapped_column(FlexibleJSON, default=dict, nullable=False)

    plan: Mapped["Plan"] = relationship(back_populates="rate_cards")


class TeamLeader(Base, TimestampMixin):
    __tablename__ = "team_leaders"

    id: Mapped[int] = mapped_column(Integer, Sequence("team_leader_id_seq", start=417), primary_key=True)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class Agent(Base, TimestampMixin):
    __tablename__ = "agents"

    id: Mapped[int] = mapped_column(Integer, Sequence("agent_id_seq", start=7821), primary_key=True)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    team_leader_id: Mapped[int | None] = mapped_column(ForeignKey("team_leaders.id"), nullable=True)
    site: Mapped[str | None] = mapped_column(String(80), nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    team_leader: Mapped["TeamLeader | None"] = relationship()


class Campaign(Base, TimestampMixin):
    __tablename__ = "campaigns"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(60), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class Site(Base, TimestampMixin):
    __tablename__ = "sites"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(60), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


__all__ = [
    "Vertical",
    "Retailer",
    "RetailerVertical",
    "Plan",
    "RateCard",
    "TeamLeader",
    "Agent",
    "Campaign",
    "Site",
]
