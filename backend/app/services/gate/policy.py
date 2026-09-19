"""The deterministic gate engine.

This is the only place a sale gate is decided, and it is plain control flow
over already-computed statuses. No LLM call happens here or anywhere
downstream of it -- that property is structural, not a convention: this
function's inputs are enum values and its output is an enum value.

Policy, in strict order:

    1. any applicable check that did not complete  -> HUMAN_REVIEW
    2. any critical check FAIL                     -> HOLD
    3. any critical check UNCERTAIN                -> HUMAN_REVIEW
    4. any applicable check without a terminal status -> HUMAN_REVIEW
    5. any non-critical FAIL explicitly configured BLOCKING -> HOLD
    6. otherwise                                   -> APPROVED

Rule 1 outranks rule 2 deliberately: if the system did not finish looking,
it does not get to assert *why* a sale is being stopped. Both outcomes stop
the sale, so no approval risk is introduced by the ordering.

Overrides are honoured through ``effective_status``; the machine's original
verdict is never mutated.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.core.enums import (
    TERMINAL_STATUSES,
    BlockingBehavior,
    CheckStatus,
    ExecutionStatus,
    GateDecision,
)


@dataclass
class GateInput:
    """The minimum a gate decision needs, decoupled from the ORM."""

    check_code: str
    critical: bool
    status: str
    execution_status: str
    blocking_behavior: str = BlockingBehavior.NON_BLOCKING.value


@dataclass
class GateOutcome:
    decision: GateDecision
    reason: str
    triggering_checks: list[str] = field(default_factory=list)


def apply_gate_policy(checks: list[GateInput]) -> GateOutcome:
    applicable = [c for c in checks if c.status != CheckStatus.NOT_APPLICABLE.value]

    if not applicable:
        return GateOutcome(
            decision=GateDecision.HUMAN_REVIEW,
            reason="No applicable checks were executed for this sale, so it cannot be auto-approved.",
        )

    incomplete = [c for c in applicable if c.execution_status != ExecutionStatus.COMPLETED.value]
    if incomplete:
        return GateOutcome(
            decision=GateDecision.HUMAN_REVIEW,
            reason=(
                f"{len(incomplete)} check(s) did not complete successfully, so the sale cannot be "
                "auto-approved."
            ),
            triggering_checks=[c.check_code for c in incomplete],
        )

    critical_fails = [
        c for c in applicable if c.critical and c.status == CheckStatus.FAIL.value
    ]
    if critical_fails:
        return GateOutcome(
            decision=GateDecision.HOLD,
            reason=f"{len(critical_fails)} critical check(s) failed.",
            triggering_checks=[c.check_code for c in critical_fails],
        )

    critical_uncertain = [
        c for c in applicable if c.critical and c.status == CheckStatus.UNCERTAIN.value
    ]
    if critical_uncertain:
        return GateOutcome(
            decision=GateDecision.HUMAN_REVIEW,
            reason=f"{len(critical_uncertain)} critical check(s) could not be determined automatically.",
            triggering_checks=[c.check_code for c in critical_uncertain],
        )

    non_terminal = [c for c in applicable if c.status not in {s.value for s in TERMINAL_STATUSES}]
    if non_terminal:
        return GateOutcome(
            decision=GateDecision.HUMAN_REVIEW,
            reason="Some applicable checks have no terminal result.",
            triggering_checks=[c.check_code for c in non_terminal],
        )

    blocking_fails = [
        c
        for c in applicable
        if not c.critical
        and c.status == CheckStatus.FAIL.value
        and c.blocking_behavior == BlockingBehavior.BLOCKING.value
    ]
    if blocking_fails:
        return GateOutcome(
            decision=GateDecision.HOLD,
            reason=(
                f"{len(blocking_fails)} non-critical check(s) explicitly configured as blocking "
                "failed."
            ),
            triggering_checks=[c.check_code for c in blocking_fails],
        )

    return GateOutcome(
        decision=GateDecision.APPROVED,
        reason="All applicable critical checks passed and every check produced a terminal result.",
    )
