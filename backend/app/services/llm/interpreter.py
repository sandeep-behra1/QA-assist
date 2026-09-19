"""Evidence interpreters.

An interpreter answers one narrow question: "looking only at these
transcript segments, does this criterion appear to be met, and which
segments show it?" Its answer is a proposal that the deterministic evaluator
may accept, downgrade, or reject outright.

Two guarantees hold regardless of implementation:
  * a PASS with no valid cited segment is never accepted (enforced in the
    semantic evaluator, not here -- defence in depth);
  * any failure, timeout, or malformed response degrades to UNCERTAIN.
"""

from __future__ import annotations

import json
import re
import time
import urllib.error
import urllib.request
from abc import ABC, abstractmethod
from dataclasses import dataclass

from pydantic import ValidationError

from app.core.config import GROQ_BASE_URL, Settings, get_settings
from app.core.enums import ConfidenceLevel
from app.models import CheckDefinition, TranscriptSegment
from app.services.llm.schemas import InterpreterCall, StructuredInterpretation
from app.services.rules.sources import get_authoritative_value


@dataclass(frozen=True)
class InterpretationResult:
    interpretation: StructuredInterpretation
    call: InterpreterCall


class EvidenceInterpreter(ABC):
    provider_name: str = "unknown"

    @abstractmethod
    def evaluate(
        self,
        check: CheckDefinition,
        transcript_segments: list[TranscriptSegment],
        authoritative_context: dict,
    ) -> InterpretationResult: ...


def _uncertain(reason: str) -> StructuredInterpretation:
    return StructuredInterpretation(
        decision="UNCERTAIN", confidence_level=ConfidenceLevel.LOW, reason=reason
    )


class MockEvidenceInterpreter(EvidenceInterpreter):
    """Deterministic offline stand-in used by default.

    It scores each candidate segment by how many of the check's configured
    ``semantic_keywords`` it contains. This is not meant to be clever -- it
    exists so the whole system, including the "LLM said PASS" path, can be
    demonstrated and tested with no API key and no network.
    """

    provider_name = "mock"

    def evaluate(
        self,
        check: CheckDefinition,
        transcript_segments: list[TranscriptSegment],
        authoritative_context: dict,
    ) -> InterpretationResult:
        started = time.perf_counter()
        config = check.evaluation_config or {}
        keywords: list[str] = [k.lower() for k in config.get("semantic_keywords", [])]
        min_hits = int(config.get("semantic_min_keywords", 2))

        if not keywords:
            interpretation = _uncertain("No semantic criteria configured for this check.")
            return self._result(interpretation, check, started)

        best_segment: TranscriptSegment | None = None
        best_hits = 0
        for segment in transcript_segments:
            lowered = segment.text.lower()
            hits = sum(1 for keyword in keywords if keyword in lowered)
            if hits > best_hits:
                best_hits, best_segment = hits, segment

        if best_segment is None or best_hits == 0:
            interpretation = _uncertain(
                "No candidate segment matched the configured semantic criteria; "
                "cannot confirm without transcript evidence."
            )
        elif best_hits >= min_hits:
            interpretation = StructuredInterpretation(
                decision="PASS",
                confidence_level=(
                    ConfidenceLevel.HIGH if best_hits > min_hits else ConfidenceLevel.MEDIUM
                ),
                evidence_segment_ids=[best_segment.segment_id],
                observed_value=best_segment.text,
                reason=f"Segment matched {best_hits}/{len(keywords)} configured criteria keywords.",
            )
        else:
            interpretation = StructuredInterpretation(
                decision="UNCERTAIN",
                confidence_level=ConfidenceLevel.LOW,
                evidence_segment_ids=[best_segment.segment_id],
                observed_value=best_segment.text,
                reason=(
                    f"Only {best_hits}/{len(keywords)} criteria keywords matched "
                    f"(minimum {min_hits}); evidence is too weak to confirm."
                ),
            )
        return self._result(interpretation, check, started)

    def _result(
        self, interpretation: StructuredInterpretation, check: CheckDefinition, started: float
    ) -> InterpretationResult:
        return InterpretationResult(
            interpretation=interpretation,
            call=InterpreterCall(
                provider=self.provider_name,
                model="deterministic-keyword-v1",
                prompt_version="n/a",
                evaluation_method=check.evaluation_method,
                latency_ms=round((time.perf_counter() - started) * 1000, 3),
                succeeded=True,
            ),
        )


USER_AGENT = "cimet-qa-gate/0.2"

RETRYABLE_STATUS = {429, 503}
MAX_RETRIES = 2
MAX_RETRY_WAIT_SECONDS = 8.0

_RETRY_HINT_RE = re.compile(r"try again in\s+([0-9]+(?:\.[0-9]+)?)\s*(ms|s)", re.IGNORECASE)
_ORG_ID_RE = re.compile(r"org_[A-Za-z0-9]+")


def _read_error_body(exc: urllib.error.HTTPError) -> str:
    try:
        return exc.read().decode("utf-8", errors="replace")
    except Exception:  # noqa: BLE001 - diagnostics must never raise
        return ""


def _suggested_wait(exc: urllib.error.HTTPError, attempt: int) -> float:
    """How long the provider says to wait, else a short exponential backoff."""
    retry_after = exc.headers.get("Retry-After") if exc.headers else None
    if retry_after:
        try:
            return float(retry_after)
        except ValueError:
            pass
    match = _RETRY_HINT_RE.search(getattr(exc, "cached_body", "") or "")
    if match:
        seconds = float(match.group(1)) / (1000 if match.group(2).lower() == "ms" else 1)
        return seconds + 0.25  # small margin so the window has actually reset
    return 1.5 * (attempt + 1)


def _describe_failure(exc: Exception) -> str:
    """A diagnosable message for a failed provider call.

    "HTTP Error 404" alone is not actionable; the provider's own error body
    ("The model `x` does not exist") is. Provider error bodies describe the
    request, not credentials, but they can name the account's organisation, so
    those ids are masked before the text is stored or shown.
    """
    if isinstance(exc, urllib.error.HTTPError):
        raw = getattr(exc, "cached_body", None)
        if raw is None:
            raw = _read_error_body(exc)
        try:
            message = json.loads(raw).get("error", {}).get("message") or raw
        except Exception:  # noqa: BLE001 - diagnostics must never raise
            message = raw
        text = f"HTTP {exc.code} {exc.reason}: {str(message)[:300]}".strip()
    else:
        text = f"{type(exc).__name__}: {exc}"
    return _ORG_ID_RE.sub("org_***", text)


class OpenAICompatibleInterpreter(EvidenceInterpreter):
    """Adapter for an OpenAI-compatible /chat/completions endpoint.

    Serves both LLM_PROVIDER=groq (the intended real provider) and a generic
    LLM_PROVIDER=openai_compatible. The response must parse as JSON and
    validate against StructuredInterpretation; anything else -- a missing key,
    network error, rate limit (HTTP 429), non-200, prose instead of JSON, an
    invented field -- is converted to UNCERTAIN and flagged as a failed call.
    """

    def __init__(self, settings: Settings | None = None):
        self._settings = settings or get_settings()
        self.provider_name = self._settings.llm_provider

    def _post(self, request: urllib.request.Request) -> dict:
        """POST with a small, bounded retry for transient provider pushback.

        Only HTTP 429 (rate limit) and 503 are retried, at most MAX_RETRIES
        times, and only when the provider's own suggested wait is short. A long
        wait fails fast: scoring is a synchronous request, and the safe outcome
        of an unavailable model is UNCERTAIN, not a hung page.
        """
        for attempt in range(MAX_RETRIES + 1):
            try:
                with urllib.request.urlopen(
                    request, timeout=self._settings.llm_timeout_seconds
                ) as response:
                    return json.loads(response.read())
            except urllib.error.HTTPError as exc:
                exc.cached_body = _read_error_body(exc)  # type: ignore[attr-defined]
                if exc.code not in RETRYABLE_STATUS or attempt == MAX_RETRIES:
                    raise
                wait = _suggested_wait(exc, attempt)
                if wait > MAX_RETRY_WAIT_SECONDS:
                    raise
                time.sleep(wait)
        raise RuntimeError("unreachable")  # pragma: no cover

    def _base_url(self) -> str:
        default = GROQ_BASE_URL if self._settings.llm_provider == "groq" else "https://api.openai.com/v1"
        return (self._settings.llm_base_url or default).rstrip("/")

    def evaluate(
        self,
        check: CheckDefinition,
        transcript_segments: list[TranscriptSegment],
        authoritative_context: dict,
    ) -> InterpretationResult:
        started = time.perf_counter()
        settings = self._settings

        if not settings.llm_api_key:
            key_name = "GROQ_API_KEY" if settings.llm_provider == "groq" else "LLM_API_KEY"
            return self._result(
                _uncertain(f"LLM provider '{settings.llm_provider}' is enabled but {key_name} is not set."),
                check,
                started,
                succeeded=False,
                error="missing_api_key",
            )

        try:
            payload = json.dumps(
                {
                    "model": settings.llm_model,
                    "temperature": 0,
                    "response_format": {"type": "json_object"},
                    "messages": [
                        {"role": "system", "content": _SYSTEM_PROMPT},
                        {
                            "role": "user",
                            "content": self._build_prompt(
                                check, transcript_segments, authoritative_context
                            ),
                        },
                    ],
                }
            ).encode("utf-8")

            request = urllib.request.Request(
                f"{self._base_url()}/chat/completions",
                data=payload,
                headers={
                    "Authorization": f"Bearer {settings.llm_api_key}",
                    "Content-Type": "application/json",
                    # Cloudflare-fronted APIs (Groq included) reject the
                    # default "Python-urllib" agent with a 403.
                    "User-Agent": USER_AGENT,
                    "Accept": "application/json",
                },
                method="POST",
            )
            body = self._post(request)

            content = body["choices"][0]["message"]["content"]
            interpretation = StructuredInterpretation.model_validate(json.loads(content))
            return self._result(interpretation, check, started, succeeded=True)
        except (ValidationError, KeyError, IndexError, ValueError, TypeError, OSError) as exc:
            detail = _describe_failure(exc)
            return self._result(
                _uncertain(f"Interpreter call failed or returned malformed output: {detail}"),
                check,
                started,
                succeeded=False,
                error=detail[:500],
            )

    def _build_prompt(
        self,
        check: CheckDefinition,
        transcript_segments: list[TranscriptSegment],
        authoritative_context: dict,
    ) -> str:
        segments = "\n".join(
            f"[{s.segment_id}] {s.speaker} ({s.start_time:.2f}-{s.end_time:.2f}s): {s.text}"
            for s in transcript_segments
        )
        config = check.evaluation_config or {}

        prompt = (
            f"Check: {check.name}\n"
            f"What must be true: {check.description}\n"
            f"Criteria: {config.get('criteria', check.description)}\n\n"
        )

        # Data minimisation: CRM fields (email, DOB, address, NMI...) are NOT
        # sent to the provider by default. A rule must explicitly list the
        # sources it needs, e.g. "llm_context_sources": ["PLAN.name"].
        context = {}
        for source in config.get("llm_context_sources") or []:
            lookup = get_authoritative_value(source, authoritative_context)
            if lookup.found:
                context[source] = lookup.value
        if context:
            prompt += (
                "Reference values (read-only; never cite these as evidence): "
                f"{json.dumps(context, default=str)}\n\n"
            )

        return prompt + f"Transcript segments (cite ONLY these ids):\n{segments}\n"

    def _result(
        self,
        interpretation: StructuredInterpretation,
        check: CheckDefinition,
        started: float,
        succeeded: bool = True,
        error: str | None = None,
    ) -> InterpretationResult:
        return InterpretationResult(
            interpretation=interpretation,
            call=InterpreterCall(
                provider=self.provider_name,
                model=self._settings.llm_model,
                prompt_version=self._settings.llm_prompt_version,
                evaluation_method=check.evaluation_method,
                latency_ms=round((time.perf_counter() - started) * 1000, 3),
                succeeded=succeeded,
                error=error,
            ),
        )


_SYSTEM_PROMPT = (
    "You interpret call-transcript evidence for a single compliance QA check. "
    "Reply with ONLY a JSON object: "
    '{"decision": "PASS|FAIL|UNCERTAIN", "confidence_level": "HIGH|MEDIUM|LOW", '
    '"evidence_segment_ids": [<int>], "observed_value": "<string or null>", "reason": "<string>"}. '
    "Rules you must follow: cite only segment ids that appear in the provided transcript; "
    "never invent a segment id, a quote, or a customer/plan value; if the transcript does not "
    "clearly show the criterion being met, answer UNCERTAIN rather than guessing. You are not "
    "deciding whether the sale is approved -- only what the transcript shows."
)


def get_evidence_interpreter(settings: Settings | None = None) -> EvidenceInterpreter:
    settings = settings or get_settings()
    if settings.llm_provider in {"groq", "openai_compatible"}:
        return OpenAICompatibleInterpreter(settings)
    return MockEvidenceInterpreter()
