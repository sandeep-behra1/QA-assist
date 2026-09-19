"""Demo tooling: the data browser/editor, presets, reset, and the re-score story."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings

RATE_MISMATCH = 3613827  # agent quotes 31.9c, the rate card says 33.14c  -> HOLD
EMAIL_MISMATCH = 3613944  # agent reads back bigpond.com, CRM says outlook.com -> HOLD


def score(client: TestClient, lead_id: int) -> dict:
    response = client.post(f"/leads/{lead_id}/score")
    assert response.status_code == 201
    return response.json()


def check(run: dict, code: str) -> dict:
    return next(r for r in run["check_results"] if r["check_code"] == code)


# ---------------------------------------------------------------------------
# Gating
# ---------------------------------------------------------------------------


def test_demo_routes_do_not_exist_when_demo_mode_is_off(seeded_client: TestClient, monkeypatch):
    monkeypatch.setattr("app.api.demo.get_settings", lambda: Settings(demo_mode=False))
    for method, path in [("get", "/demo/status"), ("get", "/demo/tables/leads"), ("post", "/demo/reset")]:
        assert getattr(seeded_client, method)(path).status_code == 404


def test_health_reports_whether_demo_mode_is_on(client: TestClient):
    assert client.get("/health").json()["demo_mode"] is True  # conftest turns it on


# ---------------------------------------------------------------------------
# Browsing
# ---------------------------------------------------------------------------


def test_status_lists_tables_with_row_counts_and_editable_columns(seeded_client: TestClient):
    body = seeded_client.get("/demo/status").json()
    tables = {t["name"]: t for t in body["tables"]}
    assert tables["leads"]["rows"] == 7
    assert "customer_email" in tables["leads"]["editable_columns"]
    assert "peak_rate" in tables["rate_cards"]["editable_columns"]
    assert tables["check_results"]["editable_columns"] == []  # history is read-only
    assert body["presets"] >= 10


def test_a_table_can_be_read_a_page_at_a_time(seeded_client: TestClient):
    page = seeded_client.get("/demo/tables/leads?limit=3&offset=0").json()
    assert page["total"] == 7 and len(page["rows"]) == 3 and page["primary_key"] == "id"
    editable = {c["name"] for c in page["columns"] if c["editable"]}
    assert "customer_email" in editable and "id" not in editable

    second = seeded_client.get("/demo/tables/leads?limit=3&offset=3").json()
    assert {r["id"] for r in page["rows"]}.isdisjoint({r["id"] for r in second["rows"]})


def test_unknown_tables_and_bad_paging_are_rejected(seeded_client: TestClient):
    assert seeded_client.get("/demo/tables/pg_user").status_code == 404
    assert seeded_client.get("/demo/tables/leads?limit=100000").status_code == 422


def test_presets_describe_every_scenario_with_an_expected_gate(client: TestClient):
    presets = client.get("/demo/presets").json()
    assert {p["expected_gate"] for p in presets} == {"APPROVED", "HOLD", "HUMAN_REVIEW"}
    first = presets[0]
    assert first["filename"].endswith(".wav") and first["preset"]["lead_id"]


# ---------------------------------------------------------------------------
# Editing is narrow and audited
# ---------------------------------------------------------------------------


def edit(client: TestClient, table: str, row_id: int, changes: dict):
    return client.patch(f"/demo/tables/{table}/{row_id}", json={"changes": changes})


def test_an_edit_returns_before_and_after_and_is_audited(seeded_client: TestClient):
    response = edit(seeded_client, "leads", EMAIL_MISMATCH, {"customer_email": "m.okafor@bigpond.com"})
    assert response.status_code == 200
    body = response.json()
    assert body["changed"] is True
    assert body["changes"]["customer_email"] == {"before": "m.okafor@outlook.com", "after": "m.okafor@bigpond.com"}

    events = seeded_client.get(f"/leads/{EMAIL_MISMATCH}/audit-events").json()
    edited = next(e for e in events if e["event_type"] == "DATA_EDITED")
    assert edited["details"]["table"] == "leads"
    assert edited["details"]["changes"]["customer_email"]["after"] == "m.okafor@bigpond.com"


def test_an_edit_that_changes_nothing_writes_no_audit_event(seeded_client: TestClient):
    assert edit(seeded_client, "leads", EMAIL_MISMATCH, {"customer_email": "m.okafor@outlook.com"}).json()["changed"] is False
    events = seeded_client.get(f"/leads/{EMAIL_MISMATCH}/audit-events").json()
    assert not any(e["event_type"] == "DATA_EDITED" for e in events)


@pytest.mark.parametrize(
    "table,row,changes",
    [
        ("leads", RATE_MISMATCH, {"id": 1}),  # primary key
        ("leads", RATE_MISMATCH, {"vertical_id": 2}),  # not whitelisted
        ("rate_cards", 5001, {"plan_id": 1}),
        ("check_results", 1, {"status": "PASS"}),  # results are history
        ("check_definitions", 1, {"critical": False}),  # published rules are immutable
        ("audit_events", 1, {"actor": "someone-else"}),  # the audit trail is append-only
    ],
)
def test_only_whitelisted_columns_of_whitelisted_tables_can_be_edited(seeded_client, table, row, changes):
    response = edit(seeded_client, table, row, changes)
    assert response.status_code in (404, 422)
    if response.status_code == 422:
        assert "cannot be edited" in response.json()["detail"] or "read-only" in response.json()["detail"]


def test_values_are_validated_against_the_column_type(seeded_client: TestClient):
    card_id = seeded_client.get("/demo/tables/rate_cards").json()["rows"][0]["id"]
    assert edit(seeded_client, "rate_cards", card_id, {"peak_rate": "cheap"}).status_code == 422
    assert edit(seeded_client, "leads", RATE_MISMATCH, {"customer_dob": "not a date"}).status_code == 422
    assert edit(seeded_client, "leads", RATE_MISMATCH, {"attributes": "[1, 2"}).status_code == 422
    assert edit(seeded_client, "leads", 999, {"customer_name": "x"}).status_code == 404


def test_json_attributes_can_be_edited_as_text_or_object(seeded_client: TestClient):
    response = edit(seeded_client, "leads", RATE_MISMATCH, {"attributes": '{"fuel_type": "ELECTRICITY", "nmi": "6305512480", "life_support": false, "concession": false, "move_in_date": "2026-10-01"}'})
    assert response.status_code == 200
    assert response.json()["row"]["attributes"]["nmi"] == "6305512480"


def test_edited_transcript_text_is_still_redacted(seeded_client: TestClient):
    segment = seeded_client.get("/demo/tables/transcript_segments?limit=1").json()["rows"][0]
    response = edit(seeded_client, "transcript_segments", segment["id"], {"text": "My card is 4111 1111 1111 1111."})
    assert "4111" not in response.json()["row"]["text"]


# ---------------------------------------------------------------------------
# The re-score story: HOLD -> fix the data -> APPROVED, with history kept
# ---------------------------------------------------------------------------


def test_fixing_the_rate_card_moves_a_hold_to_approved_and_keeps_the_old_run(seeded_client: TestClient):
    first = score(seeded_client, RATE_MISMATCH)
    assert first["gate_result"] == "HOLD"
    assert check(first, "PEAK_RATE_MATCH")["status"] == "FAIL"

    # The agent quoted 31.9c. Suppose the rate card was actually wrong.
    card = next(r for r in seeded_client.get("/demo/tables/rate_cards").json()["rows"] if r["effective_to"] is None and r["peak_rate"] == 33.14)
    assert edit(seeded_client, "rate_cards", card["id"], {"peak_rate": 31.9}).status_code == 200

    second = score(seeded_client, RATE_MISMATCH)
    assert second["gate_result"] == "APPROVED"
    assert check(second, "PEAK_RATE_MATCH")["status"] == "PASS"

    # History is intact: both runs exist and the first still says HOLD.
    runs = seeded_client.get(f"/leads/{RATE_MISMATCH}/scoring-runs").json()
    assert [r["gate_result"] for r in runs] == ["APPROVED", "HOLD"]
    assert seeded_client.get(f"/scoring-runs/{first['id']}").json()["gate_result"] == "HOLD"

    diff = seeded_client.get(f"/scoring-runs/{second['id']}/diff/{first['id']}").json()
    assert diff["gate_changed"] and (diff["base_gate"], diff["target_gate"]) == ("HOLD", "APPROVED")
    changed = {c["check_code"]: (c["before_status"], c["after_status"]) for c in diff["changes"]}
    assert changed == {"PEAK_RATE_MATCH": ("FAIL", "PASS")}
    assert diff["unchanged_count"] == len(first["check_results"]) - 1


def test_fixing_the_crm_email_moves_a_hold_to_approved(seeded_client: TestClient):
    assert score(seeded_client, EMAIL_MISMATCH)["gate_result"] == "HOLD"
    edit(seeded_client, "leads", EMAIL_MISMATCH, {"customer_email": "m.okafor@bigpond.com"})
    second = score(seeded_client, EMAIL_MISMATCH)
    assert second["gate_result"] == "APPROVED"
    assert check(second, "EMAIL_MATCH")["status"] == "PASS"


def test_correcting_a_transcript_line_moves_a_hold_to_approved(seeded_client: TestClient):
    assert score(seeded_client, RATE_MISMATCH)["gate_result"] == "HOLD"
    transcript = seeded_client.get(f"/leads/{RATE_MISMATCH}/transcript").json()
    quoted = next(s for s in transcript["segments"] if "peak usage rate" in s["text"])
    rows = seeded_client.get("/demo/tables/transcript_segments?limit=200").json()["rows"]
    row = next(r for r in rows if r["text"] == quoted["text"] and r["transcript_id"] == transcript["transcript_id"])

    edit(seeded_client, "transcript_segments", row["id"], {"text": "Your peak usage rate is thirty-three point one four cents per kilowatt hour."})
    assert score(seeded_client, RATE_MISMATCH)["gate_result"] == "APPROVED"


def test_breaking_the_data_moves_an_approved_sale_to_hold(seeded_client: TestClient):
    assert score(seeded_client, 3613790)["gate_result"] == "APPROVED"
    seeded_client.patch("/demo/tables/leads/3613790", json={"changes": {"customer_email": "someone.else@gmail.com"}})
    assert score(seeded_client, 3613790)["gate_result"] == "HOLD"


def test_only_runs_of_the_same_sale_can_be_compared(seeded_client: TestClient):
    a, b = score(seeded_client, RATE_MISMATCH), score(seeded_client, EMAIL_MISMATCH)
    assert seeded_client.get(f"/scoring-runs/{a['id']}/diff/{b['id']}").status_code == 422
    assert seeded_client.get(f"/scoring-runs/{a['id']}/diff/99999999").status_code == 404


# ---------------------------------------------------------------------------
# Reset
# ---------------------------------------------------------------------------


def test_reset_restores_the_seed_and_discards_edits_and_scoring_history(seeded_client: TestClient):
    score(seeded_client, RATE_MISMATCH)
    edit(seeded_client, "leads", EMAIL_MISMATCH, {"customer_email": "changed@example.com"})

    assert seeded_client.post("/demo/reset").json()["leads"] == 7

    assert seeded_client.get(f"/leads/{RATE_MISMATCH}/scoring-runs").json() == []
    row = next(r for r in seeded_client.get("/demo/tables/leads").json()["rows"] if r["id"] == EMAIL_MISMATCH)
    assert row["customer_email"] == "m.okafor@outlook.com"
    events = seeded_client.get("/audit-events?event_type=DEMO_RESET").json()
    assert len(events) == 1
