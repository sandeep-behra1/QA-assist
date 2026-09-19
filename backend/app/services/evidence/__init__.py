"""Evidence engine: locate -> extract -> validate.

CheckDefinition
    -> locate candidate segments      (locator.py)
    -> extract observed values        (extractors.py)
    -> validate segment references    (validator.py)
    -> hand structured evidence to the evaluator
"""

from app.services.evidence.extractors import ExtractedValue, distinct_values, extract_values
from app.services.evidence.locator import LocatedScope, build_scope, locate
from app.services.evidence.validator import ValidationOutcome, validate_segment_ids

__all__ = [
    "ExtractedValue",
    "LocatedScope",
    "ValidationOutcome",
    "build_scope",
    "distinct_values",
    "extract_values",
    "locate",
    "validate_segment_ids",
]
