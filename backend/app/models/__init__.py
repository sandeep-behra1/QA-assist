"""SQLAlchemy ORM models.

Importing this package registers every mapper, which Alembic autogenerate
and the declarative relationship resolver both rely on.
"""

from app.models.audit import AuditEvent
from app.models.catalog import (
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
from app.models.checklist import CheckDefinition, Checklist, ChecklistVersion
from app.models.lead import Call, Lead
from app.models.review import HumanOverride, HumanReview
from app.models.scoring import CheckResult, Evidence, ScoringRun
from app.models.transcript import Transcript, TranscriptSegment
from app.models.transcription import TranscriptionJob

__all__ = [
    "Agent",
    "AuditEvent",
    "Call",
    "Campaign",
    "CheckDefinition",
    "CheckResult",
    "Checklist",
    "ChecklistVersion",
    "Evidence",
    "HumanOverride",
    "HumanReview",
    "Lead",
    "Plan",
    "RateCard",
    "Retailer",
    "RetailerVertical",
    "ScoringRun",
    "Site",
    "TeamLeader",
    "TranscriptionJob",
    "Transcript",
    "TranscriptSegment",
    "Vertical",
]
