from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class TableInfo(BaseModel):
    name: str
    rows: int
    editable_columns: list[str]


class DemoStatus(BaseModel):
    demo_mode: bool
    tables: list[TableInfo]
    presets: int


class ColumnInfo(BaseModel):
    name: str
    type: str
    editable: bool
    nullable: bool


class TablePage(BaseModel):
    name: str
    total: int
    limit: int
    offset: int
    primary_key: str
    columns: list[ColumnInfo]
    rows: list[dict[str, Any]]


class EditRequest(BaseModel):
    changes: dict[str, Any]
    actor: str = "demo.presenter@example.com"


class EditResult(BaseModel):
    changed: bool
    changes: dict[str, Any] = {}
    row: dict[str, Any]


class PresetOut(BaseModel):
    key: str
    filename: str
    title: str
    expected_gate: str
    demonstrates: str
    audio_generated: bool
    audio_size_bytes: int | None
    preset: dict[str, Any]


class CheckChange(BaseModel):
    check_code: str
    check_name: str
    critical: bool
    before_status: str | None
    after_status: str | None
    before_observed: str | None
    after_observed: str | None
    before_expected: str | None
    after_expected: str | None
    reason_after: str


class RunDiff(BaseModel):
    lead_id: int
    base_run_id: int
    target_run_id: int
    base_gate: str | None
    target_gate: str | None
    gate_changed: bool
    base_qa_score: float | None
    target_qa_score: float | None
    base_checklist_version_id: int | None
    target_checklist_version_id: int | None
    changes: list[CheckChange]
    unchanged_count: int
