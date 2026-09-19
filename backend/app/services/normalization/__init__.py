"""Deterministic normalisation utilities.

Every comparison the scoring engine makes runs through this package. It is
intentionally LLM-free: normalisation and equality must be reproducible and
explainable, so they stay in ordinary code.
"""

from app.services.normalization.boolean import compare_booleans, extract_boolean, normalize_boolean
from app.services.normalization.dates import compare_dates, extract_date
from app.services.normalization.email import compare_emails, extract_email, normalize_email
from app.services.normalization.identifier import (
    compare_identifiers,
    extract_identifier,
    normalize_identifier,
)
from app.services.normalization.numeric import (
    NumericReading,
    compare_numeric,
    convert_to_unit,
    extract_numeric,
    normalize_numeric_value,
)
from app.services.normalization.phone import compare_phones, extract_phone, normalize_phone
from app.services.normalization.redaction import redact_sensitive_data
from app.services.normalization.text import (
    compare_exact_text,
    contains_exact_phrase,
    contains_normalized_phrase,
    normalize_text,
    token_coverage,
)

__all__ = [
    "NumericReading",
    "compare_booleans",
    "compare_dates",
    "compare_emails",
    "compare_exact_text",
    "compare_identifiers",
    "compare_numeric",
    "compare_phones",
    "contains_exact_phrase",
    "contains_normalized_phrase",
    "convert_to_unit",
    "extract_boolean",
    "extract_date",
    "extract_email",
    "extract_identifier",
    "extract_numeric",
    "extract_phone",
    "normalize_boolean",
    "normalize_email",
    "normalize_identifier",
    "normalize_numeric_value",
    "normalize_phone",
    "normalize_text",
    "redact_sensitive_data",
    "token_coverage",
]
