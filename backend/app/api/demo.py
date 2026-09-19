"""Demo tooling endpoints. Every route 404s unless DEMO_MODE is on."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.config import BACKEND_ROOT, get_settings
from app.core.enums import AuditEventType
from app.db.session import get_db
from app.demo.scenarios import SCENARIOS
from app.schemas.demo import DemoStatus, EditRequest, EditResult, PresetOut, TablePage
from app.seed.seed_data import seed_all
from app.services.audit import record_event
from app.services.demo import data_admin

DEMO_CALLS_DIR = BACKEND_ROOT / "demo_calls"


def require_demo_mode() -> None:
    if not get_settings().demo_mode:
        # 404, not 403: outside demo mode these routes should not appear to exist.
        raise HTTPException(status_code=404, detail="Not found.")


router = APIRouter(prefix="/demo", tags=["demo"], dependencies=[Depends(require_demo_mode)])


@router.get("/status", response_model=DemoStatus)
def status(db: Session = Depends(get_db)) -> DemoStatus:
    return DemoStatus(demo_mode=True, tables=data_admin.list_tables(db), presets=len(SCENARIOS))


@router.get("/presets", response_model=list[PresetOut])
def presets() -> list[PresetOut]:
    out = []
    for scenario in SCENARIOS:
        path = DEMO_CALLS_DIR / scenario.filename
        out.append(
            PresetOut(
                key=scenario.key,
                filename=scenario.filename,
                title=scenario.title,
                expected_gate=scenario.expected_gate,
                demonstrates=scenario.demonstrates,
                audio_generated=path.is_file(),
                audio_size_bytes=path.stat().st_size if path.is_file() else None,
                preset=scenario.preset,
            )
        )
    return out


@router.get("/tables/{name}", response_model=TablePage)
def read_table(
    name: str,
    limit: int = Query(default=50, ge=1, le=data_admin.MAX_LIMIT),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
) -> dict:
    try:
        return data_admin.read_table(db, name, limit=limit, offset=offset)
    except data_admin.UnknownTableError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.patch("/tables/{name}/{row_id}", response_model=EditResult)
def edit_row(name: str, row_id: int, payload: EditRequest, db: Session = Depends(get_db)) -> dict:
    try:
        return data_admin.edit_row(db, name, row_id, payload.changes, actor=payload.actor)
    except data_admin.UnknownTableError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except data_admin.RowNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except data_admin.DemoDataError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/reset")
def reset(db: Session = Depends(get_db)) -> dict:
    """Wipe every row and reseed. Destroys all scoring history."""
    result = seed_all(db, reset=True, demo_audio=True)
    record_event(
        db,
        event_type=AuditEventType.DEMO_RESET,
        entity_type="database",
        entity_id="all",
        actor="demo",
        details=result,
    )
    db.commit()
    return result
