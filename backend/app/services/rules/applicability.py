"""Check applicability.

``applicable_conditions`` lets a checklist say "only run the gas meter check
when fuel_type includes GAS" as data. A check that does not apply resolves
to NOT_APPLICABLE -- which is a terminal, auditable outcome, not a silent
skip.
"""

from __future__ import annotations

from typing import Any

from app.services.rules.sources import get_authoritative_value


def is_applicable(applicable_conditions: dict | None, context: dict) -> tuple[bool, str]:
    """Evaluate a check's applicability conditions against the lead context.

    Supported forms per condition value:
        "ELECTRICITY"              -> equality (case-insensitive for strings)
        ["ELECTRICITY", "DUAL"]    -> membership
        {"exists": true}           -> source must be present
        {"not": "GAS"}             -> inequality
    """
    if not applicable_conditions:
        return True, ""

    for source_path, expectation in applicable_conditions.items():
        lookup = get_authoritative_value(source_path, context)

        if isinstance(expectation, dict) and "exists" in expectation:
            if bool(expectation["exists"]) != lookup.found:
                return False, f"{source_path} presence does not match condition."
            continue

        if not lookup.found:
            return False, f"{source_path} is not present on this lead."

        if isinstance(expectation, dict) and "not" in expectation:
            if _equals(lookup.value, expectation["not"]):
                return False, f"{source_path} equals the excluded value."
            continue

        if isinstance(expectation, list):
            if not any(_equals(lookup.value, option) for option in expectation):
                return False, f"{source_path}={lookup.value!r} is not in {expectation!r}."
            continue

        if not _equals(lookup.value, expectation):
            return False, f"{source_path}={lookup.value!r} does not equal {expectation!r}."

    return True, ""


def _equals(left: Any, right: Any) -> bool:
    if isinstance(left, str) and isinstance(right, str):
        return left.strip().lower() == right.strip().lower()
    return left == right
