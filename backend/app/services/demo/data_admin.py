"""Browse the database and make audited edits, for demonstrating re-scoring.

The point of this module is the demo story "this sale is on HOLD; fix the
underlying data; re-score; it is now APPROVED, and the old run is still there".
It is deliberately narrow:

  * only whitelisted tables can be read, and only whitelisted COLUMNS edited --
    checklist rules, check results, evidence, overrides and audit rows can be
    viewed but never changed (published checklists stay immutable; history stays
    history);
  * no raw SQL;
  * every edit is written to the audit trail with before and after values;
  * it is only reachable when DEMO_MODE is on.
"""

from __future__ import annotations

import json
from datetime import date, datetime
from typing import Any

from sqlalchemy import Boolean, Date, DateTime, Float, Integer, JSON, String, Text, func, select
from sqlalchemy import BigInteger
from sqlalchemy.orm import Session

from app.core.enums import AuditEventType
from app.db.base import Base
from app.models import Transcript
from app.services.audit import json_safe, record_event
from app.services.normalization import redact_sensitive_data

# Order the browser lists tables in: the ones a demo touches first.
TABLE_ORDER = [
    "leads",
    "rate_cards",
    "transcript_segments",
    "transcripts",
    "calls",
    "scoring_runs",
    "check_results",
    "evidence",
    "human_overrides",
    "human_reviews",
    "check_definitions",
    "checklist_versions",
    "checklists",
    "plans",
    "retailers",
    "verticals",
    "agents",
    "team_leaders",
    "transcription_jobs",
    "audit_events",
]

# table -> columns a demo may change.
EDITABLE: dict[str, frozenset[str]] = {
    "leads": frozenset(
        {
            "customer_name",
            "customer_email",
            "customer_phone",
            "customer_dob",
            "address_line1",
            "suburb",
            "state",
            "postcode",
            "campaign",
            "call_datetime",
            "attributes",
        }
    ),
    "rate_cards": frozenset(
        {
            "peak_rate",
            "off_peak_rate",
            "shoulder_rate",
            "daily_supply_charge",
            "discount_percent",
            "effective_from",
            "effective_to",
        }
    ),
    "transcript_segments": frozenset({"text"}),
}

MAX_LIMIT = 200


class DemoDataError(ValueError):
    pass


class UnknownTableError(LookupError):
    pass


class RowNotFoundError(LookupError):
    pass


def _table(name: str):
    if name not in TABLE_ORDER or name not in Base.metadata.tables:
        raise UnknownTableError(f"Table '{name}' is not available in the demo browser.")
    return Base.metadata.tables[name]


def list_tables(db: Session) -> list[dict]:
    result = []
    for name in TABLE_ORDER:
        table = Base.metadata.tables.get(name)
        if table is None:
            continue
        count = db.scalar(select(func.count()).select_from(table)) or 0
        result.append(
            {"name": name, "rows": count, "editable_columns": sorted(EDITABLE.get(name, ()))}
        )
    return result


def _jsonable(value: Any) -> Any:
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    return json_safe(value)


def read_table(db: Session, name: str, limit: int = 50, offset: int = 0) -> dict:
    table = _table(name)
    limit = max(1, min(limit, MAX_LIMIT))
    total = db.scalar(select(func.count()).select_from(table)) or 0
    primary = list(table.primary_key.columns)[0]
    rows = db.execute(select(table).order_by(primary.desc()).limit(limit).offset(max(offset, 0))).mappings().all()

    editable = EDITABLE.get(name, frozenset())
    return {
        "name": name,
        "total": total,
        "limit": limit,
        "offset": offset,
        "primary_key": primary.name,
        "columns": [
            {"name": c.name, "type": type(c.type).__name__, "editable": c.name in editable, "nullable": c.nullable}
            for c in table.columns
        ],
        "rows": [{key: _jsonable(value) for key, value in row.items()} for row in rows],
    }


def _coerce(column, value: Any) -> Any:
    if value is None or (isinstance(value, str) and value.strip() == "" and column.nullable):
        if not column.nullable:
            raise DemoDataError(f"'{column.name}' cannot be empty.")
        return None

    kind = column.type
    try:
        if isinstance(kind, Boolean):
            if isinstance(value, bool):
                return value
            if str(value).strip().lower() in {"true", "yes", "1"}:
                return True
            if str(value).strip().lower() in {"false", "no", "0"}:
                return False
            raise ValueError
        if isinstance(kind, (Integer, BigInteger)):
            return int(value)
        if isinstance(kind, Float):
            return float(value)
        if isinstance(kind, DateTime):
            return value if isinstance(value, datetime) else datetime.fromisoformat(str(value))
        if isinstance(kind, Date):
            return value if isinstance(value, date) else date.fromisoformat(str(value)[:10])
        if isinstance(kind, JSON) or type(kind).__name__ in {"JSON", "JSONB", "FlexibleJSON"}:
            parsed = json.loads(value) if isinstance(value, str) else value
            if not isinstance(parsed, (dict, list)):
                raise ValueError
            return parsed
        if isinstance(kind, (String, Text)):
            return str(value)
    except (ValueError, TypeError, json.JSONDecodeError) as exc:
        raise DemoDataError(f"'{column.name}' expects a {type(kind).__name__} value; got {value!r}.") from exc
    return value


def edit_row(db: Session, name: str, row_id: int, changes: dict[str, Any], actor: str = "demo") -> dict:
    table = _table(name)
    allowed = EDITABLE.get(name)
    if not allowed:
        raise DemoDataError(f"Table '{name}' is read-only in the demo editor.")
    if not changes:
        raise DemoDataError("No changes were supplied.")

    forbidden = sorted(set(changes) - allowed)
    if forbidden:
        raise DemoDataError(
            f"Column(s) {forbidden} cannot be edited in '{name}'. Editable: {sorted(allowed)}."
        )

    primary = list(table.primary_key.columns)[0]
    current = db.execute(select(table).where(primary == row_id)).mappings().first()
    if current is None:
        raise RowNotFoundError(f"{name} row {row_id} was not found.")

    updates: dict[str, Any] = {}
    for column_name, raw in changes.items():
        value = _coerce(table.columns[column_name], raw)
        if name == "transcript_segments" and column_name == "text" and isinstance(value, str):
            value = redact_sensitive_data(value)
        updates[column_name] = value

    diff = {
        col: {"before": _jsonable(current[col]), "after": _jsonable(new)}
        for col, new in updates.items()
        if _jsonable(current[col]) != _jsonable(new)
    }
    if not diff:
        return {"changed": False, "row": {k: _jsonable(v) for k, v in current.items()}}

    db.execute(table.update().where(primary == row_id).values(**updates))

    record_event(
        db,
        event_type=AuditEventType.DATA_EDITED,
        entity_type=name,
        entity_id=row_id,
        actor=actor,
        lead_id=_lead_for(db, name, dict(current)),
        details={"table": name, "row_id": row_id, "changes": diff},
    )
    db.commit()

    refreshed = db.execute(select(table).where(primary == row_id)).mappings().first()
    return {"changed": True, "changes": diff, "row": {k: _jsonable(v) for k, v in refreshed.items()}}


def _lead_for(db: Session, table_name: str, row: dict) -> int | None:
    if table_name == "leads":
        return row["id"]
    if table_name == "transcript_segments":
        transcript = db.get(Transcript, row["transcript_id"])
        return transcript.lead_id if transcript else None
    return None
