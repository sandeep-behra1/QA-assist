"""Connectivity check for the configured LLM provider.

    python -m app.services.llm.selftest

Sends one tiny, synthetic (no customer data) rapport interpretation to the
configured provider and prints what came back, so you can confirm a Groq key,
model name and network path work before scoring anything. The API key is never
printed.
"""

from __future__ import annotations

import sys

from app.core.config import get_settings
from app.core.enums import CheckType, EvaluationMethod, EvidenceSource
from app.models import CheckDefinition, TranscriptSegment
from app.services.llm import get_evidence_interpreter


def main() -> int:
    settings = get_settings()
    print(f"provider : {settings.llm_provider}")
    print(f"model    : {settings.llm_model if settings.llm_provider != 'mock' else '(mock)'}")
    print(f"key set  : {settings.llm_ready if settings.llm_provider != 'mock' else 'n/a'}")

    check = CheckDefinition(
        id=0,
        checklist_version_id=0,
        code="RAPPORT",
        name="Rapport",
        description="Did the agent build rapport with the customer?",
        check_type=CheckType.BEHAVIOUR.value,
        evaluation_method=EvaluationMethod.BEHAVIOUR.value,
        evidence_source=EvidenceSource.AGENT_TRANSCRIPT.value,
        critical=False,
        active=True,
        display_order=0,
        blocking_behavior="NON_BLOCKING",
        weight=1.0,
        evaluation_config={
            "criteria": "Agent greets the customer warmly, thanks them, and offers help.",
            "semantic_keywords": ["thanks for your time", "happy to help"],
        },
        applicable_conditions={},
    )
    segments = [
        TranscriptSegment(
            id=1,
            transcript_id=0,
            segment_id=1,
            speaker="AGENT",
            start_time=0.0,
            end_time=4.0,
            text="Thanks for your time today, I'm happy to help with anything you need.",
            asr_confidence=0.97,
        )
    ]

    result = get_evidence_interpreter(settings).evaluate(check, segments, {})
    print(f"call ok  : {result.call.succeeded}   latency: {result.call.latency_ms:.0f} ms")
    if result.call.error:
        print(f"error    : {result.call.error}")
    interpretation = result.interpretation
    print(
        f"result   : {interpretation.decision} / {interpretation.confidence_level.value} "
        f"cited={interpretation.evidence_segment_ids}"
    )
    print(f"reason   : {interpretation.reason}")
    return 0 if result.call.succeeded else 1


if __name__ == "__main__":
    sys.exit(main())
