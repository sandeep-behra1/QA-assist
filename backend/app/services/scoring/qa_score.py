"""QA score calculation -- reporting only, never gating.

A sale with 17 of 18 checks passing scores 94% and can still be HOLD, if the
one failure is critical. The score exists for coaching and trend reporting;
the gate is decided entirely separately in services/gate/policy.py.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass

from app.core.enums import CheckStatus


@dataclass(frozen=True)
class ScoreInput:
    critical: bool
    status: str
    weight: float = 1.0


@dataclass(frozen=True)
class QaScore:
    raw_percent: float | None
    weighted_percent: float | None
    applicable_checks: int
    executed_checks: int
    pass_count: int
    fail_count: int
    uncertain_count: int
    not_applicable_count: int
    critical_fail_count: int
    critical_uncertain_count: int
    non_critical_fail_count: int

    def as_dict(self) -> dict:
        return asdict(self)


def calculate_qa_score(checks: list[ScoreInput]) -> QaScore:
    applicable = [c for c in checks if c.status != CheckStatus.NOT_APPLICABLE.value]

    pass_count = sum(1 for c in applicable if c.status == CheckStatus.PASS.value)
    fail_count = sum(1 for c in applicable if c.status == CheckStatus.FAIL.value)
    uncertain_count = sum(1 for c in applicable if c.status == CheckStatus.UNCERTAIN.value)
    not_applicable = len(checks) - len(applicable)

    raw = (pass_count / len(applicable) * 100) if applicable else None

    total_weight = sum(c.weight for c in applicable)
    weighted = (
        sum(c.weight for c in applicable if c.status == CheckStatus.PASS.value) / total_weight * 100
        if total_weight
        else None
    )

    return QaScore(
        raw_percent=round(raw, 1) if raw is not None else None,
        weighted_percent=round(weighted, 1) if weighted is not None else None,
        applicable_checks=len(applicable),
        executed_checks=len(checks),
        pass_count=pass_count,
        fail_count=fail_count,
        uncertain_count=uncertain_count,
        not_applicable_count=not_applicable,
        critical_fail_count=sum(
            1 for c in applicable if c.critical and c.status == CheckStatus.FAIL.value
        ),
        critical_uncertain_count=sum(
            1 for c in applicable if c.critical and c.status == CheckStatus.UNCERTAIN.value
        ),
        non_critical_fail_count=sum(
            1 for c in applicable if not c.critical and c.status == CheckStatus.FAIL.value
        ),
    )
