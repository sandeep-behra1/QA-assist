"""End-to-end API tests, including the six demo scenarios."""

from __future__ import annotations

import io

import pytest
from fastapi.testclient import TestClient

SCENARIOS = [
    (3613790, "CLEAN_SALE", "APPROVED"),
    (3613827, "RATE_MISMATCH", "HOLD"),
    (3613944, "EMAIL_MISMATCH", "HOLD"),
    (3614071, "AMBIGUOUS_RATE_LOW_ASR", "HUMAN_REVIEW"),
    (3614158, "RATE_CORRECTED_LATER", "HUMAN_REVIEW"),
    (3614203, "DEAD_AIR", "APPROVED"),
    (3614266, "HISTORICAL_RULE_VERSION", "APPROVED"),
]


def test_health(client: TestClient):
    body = client.get("/health").json()
    assert body["status"] == "ok"
    assert body["llm_provider"] == "mock"


def test_lead_list_exposes_every_seeded_sale(seeded_client: TestClient):
    leads = seeded_client.get("/leads").json()
    assert {lead["id"] for lead in leads} == {lead_id for lead_id, _, _ in SCENARIOS}
    assert all(lead["has_transcript"] for lead in leads)


@pytest.mark.parametrize("lead_id,scenario,expected_gate", SCENARIOS)
def test_demo_scenarios_produce_the_documented_gate(
    seeded_client: TestClient, lead_id: int, scenario: str, expected_gate: str
):
    run = seeded_client.post(f"/leads/{lead_id}/score").json()
    assert run["gate_result"] == expected_gate, f"{scenario}: {run['gate_reason']}"
    assert run["status"] == "COMPLETED"
    assert run["check_results"], "a run must record every check it executed"


def test_clean_sale_passes_every_critical_check(seeded_client: TestClient):
    run = seeded_client.post("/leads/3613790/score").json()
    criticals = [r for r in run["check_results"] if r["critical"] and r["status"] != "NOT_APPLICABLE"]
    assert criticals
    assert all(r["status"] == "PASS" for r in criticals)
    assert run["qa_score_weighted"] == 100.0


def test_rate_mismatch_is_traceable_to_evidence(seeded_client: TestClient):
    run = seeded_client.post("/leads/3613827/score").json()
    rate = next(r for r in run["check_results"] if r["check_code"] == "PEAK_RATE_MATCH")

    assert rate["status"] == "FAIL"
    assert rate["observed_value"].startswith("31.9")
    assert rate["expected_value"].startswith("33.14")
    assert rate["evidence"], "a FAIL with positive evidence must cite it"
    assert rate["rule_version"]
    assert rate["evaluation_method"] == "NUMERIC"

    # The cited segment must exist in the transcript the run scored.
    transcript = seeded_client.get("/leads/3613827/transcript").json()
    segment_ids = {s["segment_id"] for s in transcript["segments"]}
    assert all(e["segment_id"] in segment_ids for e in rate["evidence"])


def test_dead_air_is_a_coaching_note_not_a_blocker(seeded_client: TestClient):
    run = seeded_client.post("/leads/3614203/score").json()
    dead_air = next(r for r in run["check_results"] if r["check_code"] == "DEAD_AIR")
    assert dead_air["status"] == "FAIL"
    assert dead_air["critical"] is False
    assert run["gate_result"] == "APPROVED"


def test_not_applicable_checks_are_reported_with_a_reason(seeded_client: TestClient):
    run = seeded_client.post("/leads/3613790/score").json()
    mirn = next(r for r in run["check_results"] if r["check_code"] == "MIRN_MATCH")
    assert mirn["status"] == "NOT_APPLICABLE"
    assert "does not apply" in mirn["reason"]


def test_scoring_runs_accumulate_rather_than_overwrite(seeded_client: TestClient):
    first = seeded_client.post("/leads/3613827/score").json()
    second = seeded_client.post("/leads/3613827/score").json()
    assert first["id"] != second["id"]

    runs = seeded_client.get("/leads/3613827/scoring-runs").json()
    assert len(runs) == 2

    original = seeded_client.get(f"/scoring-runs/{first['id']}").json()
    assert original["gate_result"] == first["gate_result"]


def test_override_flow_changes_the_gate_but_keeps_the_machine_verdict(seeded_client: TestClient):
    run = seeded_client.post("/leads/3614071/score").json()
    assert run["gate_result"] == "HUMAN_REVIEW"

    target = next(r for r in run["check_results"] if r["check_code"] == "PEAK_RATE_MATCH")
    updated = seeded_client.post(
        f"/check-results/{target['id']}/override",
        json={
            "override_status": "PASS",
            "reason_code": "TRANSCRIPTION_ERROR",
            "notes": "Listened back; the agent clearly said 33.14 cents.",
            "actor": "qa.lead@example.com",
        },
    ).json()

    assert updated["gate_result"] == "HUMAN_REVIEW"  # machine verdict preserved
    assert updated["override_gate_result"] == "APPROVED"
    assert updated["effective_gate_result"] == "APPROVED"

    overridden = next(r for r in updated["check_results"] if r["check_code"] == "PEAK_RATE_MATCH")
    assert overridden["status"] == "UNCERTAIN"
    assert overridden["effective_status"] == "PASS"
    assert overridden["overrides"][0]["reason_code"] == "TRANSCRIPTION_ERROR"
    assert overridden["overrides"][0]["original_status"] == "UNCERTAIN"


def test_override_requires_notes(seeded_client: TestClient):
    run = seeded_client.post("/leads/3614071/score").json()
    target = run["check_results"][0]
    response = seeded_client.post(
        f"/check-results/{target['id']}/override",
        json={"override_status": "PASS", "reason_code": "OTHER", "notes": ""},
    )
    assert response.status_code == 422


def test_review_queue_prioritises_uncertain_criticals(seeded_client: TestClient):
    for lead_id, _, _ in SCENARIOS:
        seeded_client.post(f"/leads/{lead_id}/score")

    queue = seeded_client.get("/reviews?queue=NEEDS_REVIEW").json()
    assert {item["lead_id"] for item in queue} == {3614071, 3614158}
    assert all(item["priority"] == 1 for item in queue)

    hold_queue = seeded_client.get("/reviews?queue=HOLD").json()
    assert {item["lead_id"] for item in hold_queue} == {3613827, 3613944}


def test_dashboard_reflects_scored_sales(seeded_client: TestClient):
    for lead_id, _, _ in SCENARIOS:
        seeded_client.post(f"/leads/{lead_id}/score")

    summary = seeded_client.get("/dashboard/summary").json()
    assert summary["total_sales"] == 7
    assert summary["scored_sales"] == 7
    assert summary["approved"] == 3
    assert summary["hold"] == 2
    assert summary["needs_human_review"] == 2
    assert summary["first_pass_yield_percent"] == pytest.approx(42.9, abs=0.1)
    assert summary["top_failing_checks"]


def test_scoring_without_a_transcript_is_refused(seeded_client: TestClient):
    verticals = {v["code"]: v["id"] for v in seeded_client.get("/verticals").json()}
    aurora = next(r for r in seeded_client.get("/retailers").json() if r["code"] == "AURORA")
    created = seeded_client.post(
        "/leads",
        json={
            "vertical_id": verticals["ENERGY"],
            "retailer_id": aurora["id"],
            "call_datetime": "2026-09-18T10:00:00",
            "customer_name": "No Transcript",
        },
    )
    assert created.status_code == 201

    response = seeded_client.post(f"/leads/{created.json()['id']}/score")
    assert response.status_code == 409
    assert "transcript" in response.json()["detail"].lower()


def test_transcript_upload_accepts_the_canonical_contract(seeded_client: TestClient):
    verticals = {v["code"]: v["id"] for v in seeded_client.get("/verticals").json()}
    retailer = seeded_client.get("/retailers").json()[0]
    lead = seeded_client.post(
        "/leads",
        json={
            "vertical_id": verticals["ENERGY"],
            "retailer_id": retailer["id"],
            "call_datetime": "2026-09-18T10:00:00",
            "customer_name": "Canonical Upload",
            "customer_email": "canon@example.com",
        },
    ).json()

    response = seeded_client.post(
        f"/leads/{lead['id']}/transcript",
        json={
            "payload": {
                "transcript_id": 999001,
                "lead_id": lead["id"],
                "call_id": 7999001,
                "source": "MANUAL_UPLOAD",
                "language": "en-AU",
                "segments": [
                    {
                        "segment_id": 1,
                        "speaker": "AGENT",
                        "start_time": 12.10,
                        "end_time": 17.85,
                        "text": "This call may be recorded for quality and compliance purposes.",
                        "asr_confidence": 0.98,
                    },
                    {
                        "segment_id": 2,
                        "speaker": "CUSTOMER",
                        "start_time": 18.20,
                        "end_time": 19.10,
                        "text": "Okay.",
                        "asr_confidence": 0.99,
                    },
                ],
            }
        },
    )
    assert response.status_code == 201
    body = response.json()
    assert len(body["segments"]) == 2
    assert body["segments"][0]["speaker"] == "AGENT"


def test_transcript_upload_rejects_malformed_payloads(seeded_client: TestClient):
    response = seeded_client.post(
        "/leads/3613790/transcript", json={"payload": {"segments": []}}
    )
    assert response.status_code == 422


def test_pasted_transcript_is_parsed(seeded_client: TestClient):
    response = seeded_client.post(
        "/leads/3613790/transcript",
        json={"pasted_text": "AGENT: Good morning.\nCUSTOMER: Hello there.\n"},
    )
    assert response.status_code == 201
    assert [s["speaker"] for s in response.json()["segments"]] == ["AGENT", "CUSTOMER"]


def test_card_numbers_are_redacted_at_ingest(seeded_client: TestClient):
    response = seeded_client.post(
        "/leads/3613790/transcript",
        json={"pasted_text": "CUSTOMER: My card is 4111 1111 1111 1111 and the CVV is 123."},
    )
    text = response.json()["segments"][0]["text"]
    assert "4111" not in text
    assert "[REDACTED]" in text


def test_audio_upload_and_ranged_playback(seeded_client: TestClient):
    payload = b"RIFF" + b"\x00" * 4096
    upload = seeded_client.post(
        "/leads/3613790/audio",
        files={"file": ("call.wav", io.BytesIO(payload), "audio/wav")},
    )
    assert upload.status_code == 201
    assert upload.json()["transcription_status"] == "NOT_STARTED"

    full = seeded_client.get("/leads/3613790/audio")
    assert full.status_code == 200
    assert full.headers["accept-ranges"] == "bytes"

    partial = seeded_client.get("/leads/3613790/audio", headers={"Range": "bytes=10-19"})
    assert partial.status_code == 206
    assert partial.headers["content-range"] == f"bytes 10-19/{len(payload)}"
    assert partial.content == payload[10:20]


def test_demo_seed_gives_some_sales_audio_and_leaves_others_without(db, client: TestClient):
    """The UI shows a player where a recording exists and a placeholder where it does not."""
    from app.seed.seed_data import DEMO_AUDIO_LEADS, seed_all

    seed_all(db, demo_audio=True)
    leads = {lead["id"]: lead for lead in client.get("/leads").json()}

    with_audio = {lead_id for lead_id, lead in leads.items() if lead["has_audio"]}
    assert with_audio == DEMO_AUDIO_LEADS
    assert len(with_audio) < len(leads), "at least one sale must exercise the placeholder"

    response = client.get(f"/leads/{next(iter(DEMO_AUDIO_LEADS))}/audio")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("audio/wav")

    without = next(lead_id for lead_id in leads if lead_id not in DEMO_AUDIO_LEADS)
    assert client.get(f"/leads/{without}/audio").status_code == 404
    assert client.get(f"/leads/{without}").json()["call"]["has_audio"] is False


def test_audio_upload_rejects_unsupported_types(seeded_client: TestClient):
    response = seeded_client.post(
        "/leads/3613790/audio",
        files={"file": ("notes.txt", io.BytesIO(b"hello"), "text/plain")},
    )
    assert response.status_code == 415


def test_published_checklist_version_cannot_be_edited_via_api(seeded_client: TestClient):
    checklist = seeded_client.get("/checklists").json()[0]
    published = [v for v in checklist["versions"] if v["status"] == "PUBLISHED"][-1]

    response = seeded_client.post(
        f"/checklist-versions/{published['id']}/checks",
        json={
            "code": "SNEAKY",
            "name": "Sneaky",
            "check_type": "VERBATIM",
            "evaluation_method": "NORMALIZED_TEXT",
            "evidence_source": "AGENT_TRANSCRIPT",
            "critical": True,
            "evaluation_config": {"required_phrases": ["anything"]},
        },
    )
    assert response.status_code == 409


def test_draft_then_publish_via_api(seeded_client: TestClient):
    checklist = seeded_client.get("/checklists").json()[0]
    current = checklist["current_version"]

    draft = seeded_client.post(
        f"/checklists/{checklist['id']}/versions",
        json={"copy_from_version_id": current["id"], "notes": "October refresh"},
    ).json()
    assert draft["status"] == "DRAFT"
    assert draft["check_count"] == current["check_count"]

    published = seeded_client.post(
        f"/checklist-versions/{draft['id']}/publish", json={"effective_from": "2026-10-01"}
    ).json()
    assert published["status"] == "PUBLISHED"
    assert published["effective_from"] == "2026-10-01"


def test_lead_validation_reports_blockers(seeded_client: TestClient):
    verticals = {v["code"]: v["id"] for v in seeded_client.get("/verticals").json()}
    retailer = seeded_client.get("/retailers").json()[0]
    lead = seeded_client.post(
        "/leads",
        json={
            "vertical_id": verticals["ENERGY"],
            "retailer_id": retailer["id"],
            "call_datetime": "2026-09-18T10:00:00",
            "customer_name": "Incomplete Lead",
        },
    ).json()

    body = seeded_client.get(f"/leads/{lead['id']}/validate").json()
    assert body["ready_to_score"] is False
    assert any("transcript" in problem.lower() for problem in body["problems"])


def test_lead_must_belong_to_a_vertical_the_retailer_trades_in(seeded_client: TestClient):
    verticals = {v["code"]: v["id"] for v in seeded_client.get("/verticals").json()}
    aurora = next(r for r in seeded_client.get("/retailers").json() if r["code"] == "AURORA")
    response = seeded_client.post(
        "/leads",
        json={
            "vertical_id": verticals["PRIVATE_HEALTH"],
            "retailer_id": aurora["id"],
            "call_datetime": "2026-09-18T10:00:00",
        },
    )
    assert response.status_code == 422


def test_audit_events_are_exposed_per_lead(seeded_client: TestClient):
    seeded_client.post("/leads/3613790/score")
    events = seeded_client.get("/leads/3613790/audit-events").json()
    types = {event["event_type"] for event in events}
    assert {"SCORING_STARTED", "SCORING_COMPLETED", "SALE_APPROVED"} <= types


def test_unknown_lead_returns_404(seeded_client: TestClient):
    assert seeded_client.get("/leads/999999999").status_code == 404
