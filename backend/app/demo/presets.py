"""Turn a scenario preset (codes and names) into a lead payload (database ids)."""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy.orm import Session

from app.core.enums import LeadStatus
from app.repositories import catalog as catalog_repo


class PresetError(LookupError):
    pass


def resolve_preset(db: Session, preset: dict) -> dict:
    vertical = catalog_repo.get_vertical_by_code(db, preset["vertical_code"])
    if vertical is None:
        raise PresetError(f"Vertical {preset['vertical_code']!r} is not in the database.")

    retailer = next((r for r in catalog_repo.list_retailers(db) if r.code == preset["retailer_code"]), None)
    if retailer is None:
        raise PresetError(f"Retailer {preset['retailer_code']!r} is not in the database.")

    plan = next(
        (p for p in catalog_repo.list_plans(db, retailer_id=retailer.id) if p.code == preset["plan_code"]), None
    )
    if plan is None:
        raise PresetError(f"Plan {preset['plan_code']!r} is not in the database.")

    agent = next((a for a in catalog_repo.list_agents(db) if a.name == preset["agent_name"]), None)
    if agent is None:
        raise PresetError(f"Agent {preset['agent_name']!r} is not in the database.")

    return {
        "lead_id": preset["lead_id"],
        "vertical_id": vertical.id,
        "retailer_id": retailer.id,
        "plan_id": plan.id,
        "agent_id": agent.id,
        "team_leader_id": agent.team_leader_id,
        "campaign": preset.get("campaign"),
        "site": agent.site,
        "call_datetime": datetime.fromisoformat(preset["call_datetime"]),
        "customer_name": preset["customer_name"],
        "customer_email": preset["customer_email"],
        "customer_phone": preset["customer_phone"],
        "customer_dob": date.fromisoformat(preset["customer_dob"]),
        "address_line1": preset["address_line1"],
        "suburb": preset["suburb"],
        "state": preset["state"],
        "postcode": preset["postcode"],
        "attributes": dict(preset["attributes"]),
        "status": LeadStatus.READY,
    }
