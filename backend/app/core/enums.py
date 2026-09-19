"""Shared vocabulary for the whole system.

These enums are the contract between the database, the services and the API.
They are deliberately centralised: a status or method string should never be
invented inline in a service or a route.
"""

from enum import Enum


class StrEnum(str, Enum):
    def __str__(self) -> str:  # pragma: no cover - cosmetic
        return self.value


class Speaker(StrEnum):
    AGENT = "AGENT"
    CUSTOMER = "CUSTOMER"
    UNKNOWN = "UNKNOWN"


class TranscriptSource(StrEnum):
    """Where a canonical transcript came from.

    The scoring engine never branches on this -- it exists for traceability
    only, so a future Whisper/Deepgram/Azure adapter needs no engine change.
    """

    MANUAL_UPLOAD = "MANUAL_UPLOAD"
    JSON_UPLOAD = "JSON_UPLOAD"
    CIMET = "CIMET"
    WHISPER = "WHISPER"
    DEEPGRAM = "DEEPGRAM"
    AZURE = "AZURE"
    OPENAI = "OPENAI"
    EMBEDDED_DEMO = "EMBEDDED_DEMO"


class TranscriptionStatus(StrEnum):
    NOT_STARTED = "NOT_STARTED"
    PENDING = "PENDING"
    AVAILABLE = "AVAILABLE"
    FAILED = "FAILED"


class TranscriptionJobStatus(StrEnum):
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class DiarizationMode(StrEnum):
    """How speakers were separated.

    CHANNEL is the trustworthy one: a dual-channel recording (agent on one
    channel, customer on the other) attributes every word deterministically.
    NONE means speakers are UNKNOWN, and checks that need to know who said
    something resolve to UNCERTAIN rather than guessing.
    """

    CHANNEL = "CHANNEL"
    EMBEDDED = "EMBEDDED"
    NONE = "NONE"


class CheckType(StrEnum):
    VERBATIM = "VERBATIM"
    FACTUAL = "FACTUAL"
    BEHAVIOUR = "BEHAVIOUR"


class EvaluationMethod(StrEnum):
    """How a check compares evidence to expectation.

    Dispatch happens on this value (see services/scoring/registry.py), which
    is what keeps rule logic in the database instead of Python branching.
    """

    EXACT_TEXT = "EXACT_TEXT"
    NORMALIZED_TEXT = "NORMALIZED_TEXT"
    EMAIL = "EMAIL"
    NUMERIC = "NUMERIC"
    DATE = "DATE"
    BOOLEAN = "BOOLEAN"
    IDENTIFIER = "IDENTIFIER"
    SEMANTIC = "SEMANTIC"
    BEHAVIOUR = "BEHAVIOUR"


class EvidenceSource(StrEnum):
    AGENT_TRANSCRIPT = "AGENT_TRANSCRIPT"
    CUSTOMER_TRANSCRIPT = "CUSTOMER_TRANSCRIPT"
    FULL_TRANSCRIPT = "FULL_TRANSCRIPT"
    CALL_METADATA = "CALL_METADATA"


class CheckStatus(StrEnum):
    PASS = "PASS"
    FAIL = "FAIL"
    UNCERTAIN = "UNCERTAIN"
    NOT_APPLICABLE = "NOT_APPLICABLE"


class ExecutionStatus(StrEnum):
    """Did the evaluator actually finish?

    Separate from CheckStatus on purpose: a check that errored is not a
    "FAIL", and must never be collapsed into PASS. The gate treats anything
    other than COMPLETED as a reason to escalate.
    """

    COMPLETED = "COMPLETED"
    INCOMPLETE = "INCOMPLETE"
    ERROR = "ERROR"


class ConfidenceLevel(StrEnum):
    """Evaluation confidence -- NOT transcription confidence.

    Deliberately coarse: an LLM's self-reported float is not meaningful
    enough to gate compliance decisions on. asr_confidence lives on the
    transcript segment and is a different concept entirely.
    """

    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


class GateDecision(StrEnum):
    APPROVED = "APPROVED"
    HOLD = "HOLD"
    HUMAN_REVIEW = "HUMAN_REVIEW"


class ChecklistVersionStatus(StrEnum):
    DRAFT = "DRAFT"
    PUBLISHED = "PUBLISHED"
    ARCHIVED = "ARCHIVED"


class BlockingBehavior(StrEnum):
    """Whether a non-critical failure blocks the sale.

    Criticality decides escalation; this decides blocking. A non-critical
    check may still be configured BLOCKING, which is the "unless explicitly
    configured otherwise" escape hatch in the policy.
    """

    BLOCKING = "BLOCKING"
    NON_BLOCKING = "NON_BLOCKING"


class LeadStatus(StrEnum):
    DRAFT = "DRAFT"
    READY = "READY"
    SCORED = "SCORED"


class ScoringRunStatus(StrEnum):
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class ReviewStatus(StrEnum):
    OPEN = "OPEN"
    CLOSED = "CLOSED"


class OverrideReasonCode(StrEnum):
    TRANSCRIPTION_ERROR = "TRANSCRIPTION_ERROR"
    EVIDENCE_MISSED = "EVIDENCE_MISSED"
    RULE_INTERPRETATION = "RULE_INTERPRETATION"
    CRM_DATA_ERROR = "CRM_DATA_ERROR"
    AGENT_CORRECTED_LATER = "AGENT_CORRECTED_LATER"
    APPROVED_EXCEPTION = "APPROVED_EXCEPTION"
    OTHER = "OTHER"


class AuditEventType(StrEnum):
    LEAD_CREATED = "LEAD_CREATED"
    LEAD_UPDATED = "LEAD_UPDATED"
    AUDIO_UPLOADED = "AUDIO_UPLOADED"
    TRANSCRIPT_UPLOADED = "TRANSCRIPT_UPLOADED"
    CHECKLIST_DRAFT_CREATED = "CHECKLIST_DRAFT_CREATED"
    CHECKLIST_VERSION_PUBLISHED = "CHECKLIST_VERSION_PUBLISHED"
    SCORING_STARTED = "SCORING_STARTED"
    SCORING_COMPLETED = "SCORING_COMPLETED"
    SALE_APPROVED = "SALE_APPROVED"
    SALE_HOLD = "SALE_HOLD"
    SALE_ROUTED_TO_REVIEW = "SALE_ROUTED_TO_REVIEW"
    HUMAN_REVIEW_OPENED = "HUMAN_REVIEW_OPENED"
    CHECK_OVERRIDDEN = "CHECK_OVERRIDDEN"
    TRANSCRIPTION_COMPLETED = "TRANSCRIPTION_COMPLETED"
    TRANSCRIPTION_FAILED = "TRANSCRIPTION_FAILED"
    DATA_EDITED = "DATA_EDITED"
    DEMO_RESET = "DEMO_RESET"


class ExtractionMethod(StrEnum):
    """How an observed value was pulled out of a transcript segment.

    Stored on every Evidence row so a reviewer can tell a regex hit from an
    LLM interpretation at a glance.
    """

    SPOKEN_EMAIL = "SPOKEN_EMAIL"
    WRITTEN_EMAIL = "WRITTEN_EMAIL"
    SPOKEN_NUMBER = "SPOKEN_NUMBER"
    WRITTEN_NUMBER = "WRITTEN_NUMBER"
    DATE_PARSE = "DATE_PARSE"
    IDENTIFIER_PARSE = "IDENTIFIER_PARSE"
    BOOLEAN_PARSE = "BOOLEAN_PARSE"
    PHRASE_MATCH = "PHRASE_MATCH"
    LLM_SEMANTIC = "LLM_SEMANTIC"
    GAP_ANALYSIS = "GAP_ANALYSIS"
    OVERLAP_ANALYSIS = "OVERLAP_ANALYSIS"


TERMINAL_STATUSES = frozenset(
    {CheckStatus.PASS, CheckStatus.FAIL, CheckStatus.UNCERTAIN, CheckStatus.NOT_APPLICABLE}
)
