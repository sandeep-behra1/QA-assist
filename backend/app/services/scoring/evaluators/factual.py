"""FACTUAL evaluation: does what was said match the authoritative record?

Order of operations is the safety design:
  1. authoritative value first -- missing ground truth ends the check as
     UNCERTAIN before any transcript is read;
  2. extract what was actually said;
  3. nothing said -> UNCERTAIN (silence is not proof of a wrong value, and
     never proof of a right one);
  4. two different values said -> UNCERTAIN unless the rule declares a
     precedence;
  5. only then, a deterministic comparison.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from app.core.enums import CheckStatus, ConfidenceLevel, EvaluationMethod, ExecutionStatus
from app.services.evidence import distinct_values, extract_values, locate
from app.services.normalization import (
    compare_booleans,
    compare_dates,
    compare_emails,
    compare_identifiers,
    compare_numeric,
    normalize_boolean,
    normalize_numeric_value,
)
from app.services.normalization.dates import extract_date
from app.services.rules.sources import get_authoritative_value
from app.services.scoring.context import (
    EvaluationContext,
    EvaluationOutcome,
    EvidenceRef,
    apply_low_confidence_policy,
    confidence_from_evidence,
)


def evaluate_factual(ctx: EvaluationContext) -> EvaluationOutcome:
    check = ctx.check
    config = check.evaluation_config or {}
    method = check.evaluation_method

    lookup = get_authoritative_value(check.expected_source, ctx.authoritative_context)
    if not lookup.found:
        return EvaluationOutcome(
            status=CheckStatus.UNCERTAIN,
            reason=(
                f"Authoritative value '{check.expected_source}' is unavailable for this lead, "
                "so the spoken value cannot be verified."
            ),
            confidence_level=ConfidenceLevel.LOW,
            expected_value=None,
        )

    expected_raw = lookup.value
    expected_display = _display(expected_raw, config)

    located = locate(ctx.segments, check.evidence_source, config.get("search_keywords"))
    if located.scope_size == 0:
        return EvaluationOutcome(
            status=CheckStatus.UNCERTAIN,
            execution_status=ExecutionStatus.INCOMPLETE,
            reason="No transcript segments were available for the configured evidence source.",
            confidence_level=ConfidenceLevel.LOW,
            expected_value=expected_display,
        )

    extracted = extract_values(
        method,
        located.candidates,
        config=config,
        expected=expected_raw,
        reference_date=ctx.reference_date,
    )

    if not extracted:
        return EvaluationOutcome(
            status=CheckStatus.UNCERTAIN,
            reason=(
                f"No statement of this value was found across {len(located.candidates)} candidate "
                f"segment(s) (of {located.scope_size} searched). Absence alone proves neither a "
                "match nor a mismatch."
            ),
            confidence_level=ConfidenceLevel.LOW,
            expected_value=expected_display,
        )

    values = distinct_values(extracted)
    if len(values) > 1:
        precedence = (config.get("conflict_precedence") or "").upper()
        if precedence not in {"FIRST", "LAST"}:
            return EvaluationOutcome(
                status=CheckStatus.UNCERTAIN,
                reason=(
                    "Conflicting values were stated during the call "
                    f"({', '.join(str(v) for v in values)}) and this rule defines no precedence, "
                    "so the correct value cannot be determined automatically."
                ),
                confidence_level=ConfidenceLevel.LOW,
                observed_value=", ".join(item.display for item in extracted),
                expected_value=expected_display,
                evidence=[
                    EvidenceRef(segment=item.segment, extraction_method=item.extraction_method)
                    for item in extracted
                ],
            )
        chosen = extracted[0] if precedence == "FIRST" else extracted[-1]
        selected = [chosen]
        precedence_note = (
            f" Rule precedence '{precedence}' selected the {'first' if precedence == 'FIRST' else 'last'} "
            "of the conflicting statements."
        )
    else:
        selected = [item for item in extracted if item.comparable == values[0]]
        precedence_note = ""

    observed = selected[0]
    matched, compare_note = _compare(method, observed.value, expected_raw, config)
    evidence = [EvidenceRef(segment=item.segment, extraction_method=item.extraction_method) for item in selected]

    outcome = EvaluationOutcome(
        status=CheckStatus.PASS if matched else CheckStatus.FAIL,
        reason=(
            ("Spoken value matches the authoritative record." if matched
             else "Spoken value does not match the authoritative record.")
            + compare_note
            + precedence_note
        ),
        confidence_level=confidence_from_evidence([item.segment for item in selected], ctx.settings),
        observed_value=observed.display,
        expected_value=expected_display,
        evidence=evidence,
    )
    return apply_low_confidence_policy(outcome, check.critical)


def _compare(method: str, observed: Any, expected_raw: Any, config: dict) -> tuple[bool, str]:
    if method == EvaluationMethod.EMAIL.value:
        return compare_emails(str(observed), str(expected_raw)), ""

    if method == EvaluationMethod.NUMERIC.value:
        expected_value = normalize_numeric_value(expected_raw)
        if expected_value is None:
            return False, " Authoritative value was not numeric."
        tolerance = float(config.get("tolerance", 0.0))
        matched = compare_numeric(float(observed), expected_value, tolerance)
        unit = config.get("unit") or ""
        return matched, f" Compared with tolerance {tolerance:g} {unit}".rstrip()

    if method == EvaluationMethod.DATE.value:
        expected_date = _coerce_date(expected_raw)
        if expected_date is None:
            return False, " Authoritative value was not a date."
        return compare_dates(observed, expected_date), ""

    if method == EvaluationMethod.BOOLEAN.value:
        expected_bool = normalize_boolean(expected_raw)
        if expected_bool is None:
            return False, " Authoritative value was not boolean."
        return compare_booleans(bool(observed), expected_bool), ""

    if method == EvaluationMethod.IDENTIFIER.value:
        return compare_identifiers(str(observed), str(expected_raw)), ""

    return False, f" Unsupported factual evaluation method '{method}'."


def _coerce_date(value: Any) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        return extract_date(value)
    return None


def _display(value: Any, config: dict) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        unit = config.get("unit") or ""
        return f"{value:g} {unit}".strip()
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    return str(value)
