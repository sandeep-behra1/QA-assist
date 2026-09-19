"""Where the LLM may and may not act, and the Groq adapter itself."""

from __future__ import annotations

import io
import json
import urllib.error

import pytest
from sqlalchemy.orm import Session

from app.core.config import (
    DEFAULT_GROQ_MODEL,
    GROQ_BASE_URL,
    Settings,
    parse_dotenv,
)
from app.core.enums import CheckType, ConfidenceLevel, EvaluationMethod, EvidenceSource
from app.models import CheckDefinition
from app.services.llm import (
    MockEvidenceInterpreter,
    OpenAICompatibleInterpreter,
    get_evidence_interpreter,
)
from app.services.llm.interpreter import InterpretationResult, USER_AGENT
from app.services.llm.schemas import StructuredInterpretation
from app.services.scoring.engine import score_lead
from tests.factories import lead_context, make_check, make_segment

SEEDED_LEADS = [3613790, 3613827, 3613944, 3614071, 3614158, 3614203, 3614266]


# --------------------------------------------------------------------------
# Where the interpreter can be reached from
# --------------------------------------------------------------------------


class SpyInterpreter(MockEvidenceInterpreter):
    """Records every check the engine hands to the model."""

    def __init__(self):
        self.consulted: list[tuple[str, bool]] = []

    def evaluate(self, check, transcript_segments, authoritative_context):
        self.consulted.append((check.code, check.critical))
        return super().evaluate(check, transcript_segments, authoritative_context)


class AlwaysPassInterpreter:
    """A hostile/over-eager model: says PASS with HIGH confidence to everything."""

    def __init__(self):
        self.calls = 0

    def evaluate(self, check, transcript_segments, authoritative_context):
        from app.services.llm.schemas import InterpreterCall

        self.calls += 1
        cited = [transcript_segments[0].segment_id] if transcript_segments else []
        return InterpretationResult(
            interpretation=StructuredInterpretation(
                decision="PASS",
                confidence_level=ConfidenceLevel.HIGH,
                evidence_segment_ids=cited,
                observed_value="everything is fine",
                reason="looks good to me",
            ),
            call=InterpreterCall(
                provider="hostile",
                model="always-pass",
                prompt_version="v1",
                evaluation_method=check.evaluation_method,
                latency_ms=0.1,
                succeeded=True,
            ),
        )


def test_only_interpretive_non_critical_checks_ever_reach_the_model(seeded_db: Session):
    spy = SpyInterpreter()
    for lead_id in SEEDED_LEADS:
        score_lead(seeded_db, lead_id, interpreter=spy)

    consulted_codes = {code for code, _ in spy.consulted}
    assert consulted_codes == {"RAPPORT", "OBJECTION_HANDLING"}
    assert not any(critical for _, critical in spy.consulted)


def test_a_model_cannot_rescue_a_deterministic_critical_fail(seeded_db: Session):
    """The scenario the design exists to prevent.

    Even a model that answers PASS/HIGH to everything cannot turn a wrong rate
    or a wrong email into an approval, because deterministic checks never
    consult it.
    """
    hostile = AlwaysPassInterpreter()

    rate = score_lead(seeded_db, 3613827, interpreter=hostile)  # wrong peak rate
    email = score_lead(seeded_db, 3613944, interpreter=hostile)  # wrong email

    assert rate.gate_result == "HOLD"
    assert email.gate_result == "HOLD"
    assert next(r for r in rate.check_results if r.check_code == "PEAK_RATE_MATCH").status == "FAIL"
    assert next(r for r in email.check_results if r.check_code == "EMAIL_MATCH").status == "FAIL"


def test_a_model_cannot_resolve_a_deterministic_uncertain(seeded_db: Session):
    hostile = AlwaysPassInterpreter()
    ambiguous = score_lead(seeded_db, 3614071, interpreter=hostile)  # low-ASR rate
    conflicting = score_lead(seeded_db, 3614158, interpreter=hostile)  # two rates stated

    assert ambiguous.gate_result == "HUMAN_REVIEW"
    assert conflicting.gate_result == "HUMAN_REVIEW"


def test_the_model_is_never_consulted_for_deterministic_methods(seeded_db: Session):
    hostile = AlwaysPassInterpreter()
    run = score_lead(seeded_db, 3613827, interpreter=hostile)

    # Only the two interpretive coaching checks produced LLM metadata.
    with_llm = {r.check_code for r in run.check_results if r.llm_metadata}
    assert with_llm == {"RAPPORT", "OBJECTION_HANDLING"}
    assert hostile.calls == 2


# --------------------------------------------------------------------------
# Provider selection and configuration
# --------------------------------------------------------------------------


def groq_settings(**overrides) -> Settings:
    base = dict(
        llm_provider="groq",
        llm_api_key="gsk_test_key_123",
        llm_base_url=GROQ_BASE_URL,
        llm_model=DEFAULT_GROQ_MODEL,
    )
    base.update(overrides)
    return Settings(**base)


def test_default_provider_is_the_offline_mock():
    interpreter = get_evidence_interpreter(Settings())
    assert isinstance(interpreter, MockEvidenceInterpreter)


def test_groq_provider_selects_the_http_adapter():
    interpreter = get_evidence_interpreter(groq_settings())
    assert isinstance(interpreter, OpenAICompatibleInterpreter)
    assert interpreter.provider_name == "groq"


def test_llm_ready_reflects_key_presence_without_exposing_it():
    assert Settings().llm_ready is True  # mock needs nothing
    assert groq_settings().llm_ready is True
    assert groq_settings(llm_api_key=None).llm_ready is False


def test_dotenv_parser_handles_comments_and_quotes():
    parsed = parse_dotenv(
        "# a comment\n"
        "LLM_PROVIDER=groq\n"
        'GROQ_API_KEY="gsk_abc"\n'
        "GROQ_MODEL=llama-3.3-70b-versatile  # trailing note\n"
        "\n"
        "EMPTY=\n"
    )
    assert parsed == {
        "LLM_PROVIDER": "groq",
        "GROQ_API_KEY": "gsk_abc",
        "GROQ_MODEL": "llama-3.3-70b-versatile",
        "EMPTY": "",
    }


# --------------------------------------------------------------------------
# The Groq adapter, with the network stubbed out
# --------------------------------------------------------------------------


def rapport_check(**config) -> CheckDefinition:
    base = {
        "criteria": "Agent greets the customer warmly.",
        "semantic_keywords": ["thanks"],
    }
    base.update(config)
    return make_check(
        code="RAPPORT",
        check_type=CheckType.BEHAVIOUR,
        method=EvaluationMethod.SEMANTIC,
        evidence_source=EvidenceSource.AGENT_TRANSCRIPT,
        critical=False,
        config=base,
    )


class FakeResponse(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def completion(content: str) -> FakeResponse:
    return FakeResponse(json.dumps({"choices": [{"message": {"content": content}}]}).encode())


@pytest.fixture
def captured(monkeypatch):
    """Replace the network call and sleeping; capture what would have been sent."""
    sent: dict = {"attempts": 0, "sleeps": []}
    monkeypatch.setattr("app.services.llm.interpreter.time.sleep", lambda s: sent["sleeps"].append(s))

    def install(response=None, error=None, script=None):
        """``script``: a list of responses/exceptions returned in order."""
        queue = list(script or [])

        def fake_urlopen(request, timeout=None):
            sent["attempts"] += 1
            sent["request"] = request
            sent["body"] = json.loads(request.data.decode())
            sent["timeout"] = timeout
            if queue:
                item = queue.pop(0)
                if isinstance(item, Exception):
                    raise item
                return item
            if error:
                raise error
            return response

        monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)

    sent["install"] = install
    return sent


SEGMENTS = [make_segment(7, "Thanks for your time today, happy to help.")]


def test_groq_request_targets_the_groq_endpoint_with_the_configured_model(captured):
    captured["install"](
        completion(
            json.dumps(
                {
                    "decision": "PASS",
                    "confidence_level": "HIGH",
                    "evidence_segment_ids": [7],
                    "observed_value": "Thanks for your time",
                    "reason": "Warm greeting.",
                }
            )
        )
    )
    interpreter = OpenAICompatibleInterpreter(groq_settings())
    result = interpreter.evaluate(rapport_check(), SEGMENTS, {})

    request = captured["request"]
    assert request.full_url == "https://api.groq.com/openai/v1/chat/completions"
    assert request.get_header("Authorization") == "Bearer gsk_test_key_123"
    assert request.get_header("User-agent") == USER_AGENT  # Cloudflare rejects urllib's default
    assert captured["body"]["model"] == DEFAULT_GROQ_MODEL
    assert captured["body"]["temperature"] == 0
    assert captured["body"]["response_format"] == {"type": "json_object"}

    assert result.interpretation.decision == "PASS"
    assert result.interpretation.evidence_segment_ids == [7]
    assert result.call.provider == "groq"
    assert result.call.model == DEFAULT_GROQ_MODEL
    assert result.call.succeeded is True


def test_crm_data_is_not_sent_to_the_provider_by_default(captured):
    captured["install"](completion(json.dumps({"decision": "UNCERTAIN", "confidence_level": "LOW"})))
    context = lead_context(email="private.person@example.com")

    OpenAICompatibleInterpreter(groq_settings()).evaluate(rapport_check(), SEGMENTS, context)

    prompt = captured["body"]["messages"][1]["content"]
    assert "private.person@example.com" not in prompt
    assert "1985" not in prompt  # DOB
    assert "Rosella" not in prompt  # address
    assert "6102001234" not in prompt  # NMI
    assert "Reference values" not in prompt
    assert "[7]" in prompt  # the transcript segment itself is what gets interpreted


def test_a_rule_can_opt_in_to_specific_reference_values(captured):
    captured["install"](completion(json.dumps({"decision": "UNCERTAIN", "confidence_level": "LOW"})))
    check = rapport_check(llm_context_sources=["PLAN.name"])

    OpenAICompatibleInterpreter(groq_settings()).evaluate(check, SEGMENTS, lead_context())

    prompt = captured["body"]["messages"][1]["content"]
    assert "Aurora Saver Plus" in prompt
    assert "private" not in prompt and "james.whitfield" not in prompt


def test_prose_instead_of_json_becomes_uncertain(captured):
    captured["install"](completion("Sure! I think the agent did great."))
    result = OpenAICompatibleInterpreter(groq_settings()).evaluate(rapport_check(), SEGMENTS, {})
    assert result.interpretation.decision == "UNCERTAIN"
    assert result.call.succeeded is False


def test_json_with_an_invalid_decision_becomes_uncertain(captured):
    captured["install"](completion(json.dumps({"decision": "APPROVED", "confidence_level": "HIGH"})))
    result = OpenAICompatibleInterpreter(groq_settings()).evaluate(rapport_check(), SEGMENTS, {})
    assert result.interpretation.decision == "UNCERTAIN"
    assert result.call.succeeded is False


@pytest.mark.parametrize("code", [401, 403, 429, 500])
def test_http_errors_including_rate_limits_become_uncertain(captured, code):
    error = urllib.error.HTTPError("https://api.groq.com", code, "error", {}, io.BytesIO(b"{}"))
    captured["install"](error=error)
    result = OpenAICompatibleInterpreter(groq_settings()).evaluate(rapport_check(), SEGMENTS, {})
    assert result.interpretation.decision == "UNCERTAIN"
    assert result.call.succeeded is False


def rate_limit(message: str, headers=None) -> urllib.error.HTTPError:
    body = json.dumps({"error": {"message": message}}).encode()
    return urllib.error.HTTPError("https://api.groq.com", 429, "Too Many Requests", headers or {}, io.BytesIO(body))


GOOD = json.dumps({"decision": "PASS", "confidence_level": "HIGH", "evidence_segment_ids": [7], "reason": "ok"})


def test_a_rate_limit_is_retried_after_the_wait_the_provider_asks_for(captured):
    captured["install"](
        script=[rate_limit("Rate limit reached. Please try again in 5.5s."), completion(GOOD)]
    )
    result = OpenAICompatibleInterpreter(groq_settings()).evaluate(rapport_check(), SEGMENTS, {})

    assert captured["attempts"] == 2
    assert captured["sleeps"] == [pytest.approx(5.75)]  # provider hint + small margin
    assert result.interpretation.decision == "PASS"
    assert result.call.succeeded is True


def test_retries_are_bounded_then_the_check_becomes_uncertain(captured):
    captured["install"](error=rate_limit("Please try again in 1s."))
    result = OpenAICompatibleInterpreter(groq_settings()).evaluate(rapport_check(), SEGMENTS, {})

    assert captured["attempts"] == 3  # the first try + 2 retries, then it stops
    assert result.interpretation.decision == "UNCERTAIN"
    assert result.call.succeeded is False


def test_a_long_provider_wait_fails_fast_instead_of_hanging_the_request(captured):
    captured["install"](error=rate_limit("Please try again in 45s."))
    result = OpenAICompatibleInterpreter(groq_settings()).evaluate(rapport_check(), SEGMENTS, {})

    assert captured["attempts"] == 1
    assert captured["sleeps"] == []
    assert result.call.succeeded is False


def test_non_transient_errors_are_not_retried(captured):
    error = urllib.error.HTTPError("https://api.groq.com", 401, "Unauthorized", {}, io.BytesIO(b"{}"))
    captured["install"](error=error)
    OpenAICompatibleInterpreter(groq_settings()).evaluate(rapport_check(), SEGMENTS, {})
    assert captured["attempts"] == 1


def test_provider_error_text_is_surfaced_but_the_org_id_is_masked(captured):
    captured["install"](
        error=rate_limit(
            "Rate limit reached in organization `org_01abc23def` on tokens per minute. "
            "Please try again in 45s."
        )
    )
    result = OpenAICompatibleInterpreter(groq_settings()).evaluate(rapport_check(), SEGMENTS, {})

    assert "Rate limit reached" in result.call.error
    assert "org_01abc23def" not in result.call.error
    assert "org_***" in result.call.error


def test_the_api_key_never_appears_in_stored_metadata(captured):
    captured["install"](error=rate_limit("Please try again in 45s."))
    result = OpenAICompatibleInterpreter(groq_settings()).evaluate(rapport_check(), SEGMENTS, {})
    assert "gsk_test_key_123" not in json.dumps(result.call.model_dump())
    assert "gsk_test_key_123" not in result.interpretation.reason


def test_objection_handling_is_given_the_customers_turns_too(seeded_db: Session):
    from app.repositories import checklists as checklist_repo

    version = checklist_repo.list_checklists(seeded_db)[0].versions[-1]
    check = next(c for c in version.checks if c.code == "OBJECTION_HANDLING")
    assert check.evidence_source == "FULL_TRANSCRIPT"


def test_timeout_becomes_uncertain(captured):
    captured["install"](error=TimeoutError("timed out"))
    result = OpenAICompatibleInterpreter(groq_settings()).evaluate(rapport_check(), SEGMENTS, {})
    assert result.interpretation.decision == "UNCERTAIN"
    assert result.call.succeeded is False


def test_missing_groq_key_makes_no_network_call_and_names_the_variable(captured):
    captured["install"](completion("{}"))
    result = OpenAICompatibleInterpreter(groq_settings(llm_api_key=None)).evaluate(
        rapport_check(), SEGMENTS, {}
    )
    assert "request" not in captured
    assert "GROQ_API_KEY" in result.interpretation.reason
    assert result.call.succeeded is False


def test_a_failed_groq_call_escalates_the_check_rather_than_passing_it(seeded_db: Session, monkeypatch):
    """End to end: Groq down => coaching checks UNCERTAIN + ERROR, never PASS."""

    def down(request, timeout=None):
        raise urllib.error.URLError("network unreachable")

    monkeypatch.setattr("urllib.request.urlopen", down)
    run = score_lead(
        seeded_db,
        3613790,
        interpreter=OpenAICompatibleInterpreter(groq_settings()),
    )

    rapport = next(r for r in run.check_results if r.check_code == "RAPPORT")
    assert rapport.status == "UNCERTAIN"
    assert rapport.execution_status == "ERROR"
    assert rapport.llm_metadata["provider"] == "groq"
    assert rapport.llm_metadata["succeeded"] is False

    # The deterministic critical checks are unaffected by the outage...
    email = next(r for r in run.check_results if r.check_code == "EMAIL_MATCH")
    assert email.status == "PASS"
    # ...but an errored applicable check can never be auto-approved.
    assert run.gate_result == "HUMAN_REVIEW"
