from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.types import BigIntPK, FlexibleJSON


class AuditEvent(Base):
    """Append-only record of everything that materially happened to a sale."""

    __tablename__ = "audit_events"

    id: Mapped[int] = mapped_column(BigIntPK, primary_key=True, autoincrement=True)
    event_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    entity_type: Mapped[str] = mapped_column(String(50), nullable=False)
    entity_id: Mapped[str] = mapped_column(String(60), nullable=False)
    lead_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, index=True)
    actor: Mapped[str] = mapped_column(String(160), nullable=False)
    details: Mapped[dict] = mapped_column(FlexibleJSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )
