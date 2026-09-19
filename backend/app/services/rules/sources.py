"""Authoritative (non-transcript) data access.

``get_authoritative_value`` is the only way an evaluator reads CRM, plan or
rate-card data. It returns a SourceLookup that distinguishes three cases
that a bare ``None`` would blur together:

    found=True,  value=<anything>   -> usable ground truth (including False!)
    found=False                     -> the source is missing -> UNCERTAIN

Conflating "concession is False" with "concession is unknown" would let a
missing CRM field silently pass a check, which is exactly the failure mode
this system exists to prevent.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.models import Call, Lead, Plan, RateCard, Retailer


@dataclass(frozen=True)
class SourceLookup:
    found: bool
    value: Any = None


def build_authoritative_context(
    lead: Lead,
    retailer: Retailer,
    plan: Plan | None,
    rate_card: RateCard | None,
    call: Call | None = None,
) -> dict:
    """Assemble the read-only snapshot evaluators compare transcripts against.

    Built from trusted database rows before evaluation starts. Nothing
    downstream -- least of all an LLM -- may write to it.
    """
    context: dict[str, Any] = {
        "LEAD": {
            "id": lead.id,
            "customer_name": lead.customer_name,
            "customer_email": lead.customer_email,
            "customer_phone": lead.customer_phone,
            "customer_dob": lead.customer_dob,
            "address_line1": lead.address_line1,
            "suburb": lead.suburb,
            "state": lead.state,
            "postcode": lead.postcode,
            "campaign": lead.campaign,
            "site": lead.site,
            "call_datetime": lead.call_datetime,
            "attributes": dict(lead.attributes or {}),
        },
        "RETAILER": {"id": retailer.id, "name": retailer.name, "code": retailer.code},
        "PLAN": None,
        "RATE_CARD": None,
        "CALL": None,
    }

    if plan is not None:
        context["PLAN"] = {
            "id": plan.id,
            "name": plan.name,
            "code": plan.code,
            "attributes": dict(plan.attributes or {}),
        }

    if rate_card is not None:
        context["RATE_CARD"] = {
            "id": rate_card.id,
            "peak_rate": rate_card.peak_rate,
            "off_peak_rate": rate_card.off_peak_rate,
            "shoulder_rate": rate_card.shoulder_rate,
            "daily_supply_charge": rate_card.daily_supply_charge,
            "discount_percent": rate_card.discount_percent,
            "currency": rate_card.currency,
            "unit": rate_card.unit,
            "attributes": dict(rate_card.attributes or {}),
        }

    if call is not None:
        context["CALL"] = {
            "id": call.id,
            "duration_seconds": call.duration_seconds,
            "transcription_status": call.transcription_status,
        }

    return context


def get_authoritative_value(expected_source: str | None, context: dict) -> SourceLookup:
    """Resolve a dotted source path (e.g. "RATE_CARD.peak_rate") safely."""
    if not expected_source:
        return SourceLookup(found=False)

    node: Any = context
    for part in expected_source.split("."):
        if not isinstance(node, dict) or part not in node:
            return SourceLookup(found=False)
        node = node[part]

    # A present-but-null authoritative field is not ground truth.
    if node is None:
        return SourceLookup(found=False)
    return SourceLookup(found=True, value=node)
