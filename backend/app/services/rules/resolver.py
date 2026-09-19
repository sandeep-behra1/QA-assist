"""Checklist version resolution.

The single place that answers "which rules applied to this call?". Only
PUBLISHED versions are ever eligible: a DRAFT being edited by a QA manager
must never be used to score a live sale.
"""

from __future__ import annotations

from datetime import date

from app.core.enums import ChecklistVersionStatus
from app.models import ChecklistVersion


class NoApplicableChecklistError(LookupError):
    def __init__(self, retailer_id: int, vertical_id: int, call_date: date):
        super().__init__(
            f"No published checklist version covers {call_date.isoformat()} "
            f"for retailer {retailer_id} / vertical {vertical_id}."
        )
        self.retailer_id = retailer_id
        self.vertical_id = vertical_id
        self.call_date = call_date


def version_covers_date(version: ChecklistVersion, call_date: date) -> bool:
    if version.status != ChecklistVersionStatus.PUBLISHED.value:
        return False
    if version.effective_from is None or version.effective_from > call_date:
        return False
    return version.effective_to is None or call_date <= version.effective_to


def resolve_checklist_version(
    versions: list[ChecklistVersion], call_date: date
) -> ChecklistVersion | None:
    """Return the published version whose effective window contains call_date.

    If windows ever overlap (bad data), the highest version number wins and
    the result is still deterministic rather than arbitrary.
    """
    matches = [v for v in versions if version_covers_date(v, call_date)]
    if not matches:
        return None
    return max(matches, key=lambda v: v.version_number)
