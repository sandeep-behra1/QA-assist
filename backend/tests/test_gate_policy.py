"""The deterministic gate policy, in isolation from everything else."""

import pytest

from app.core.enums import BlockingBehavior, CheckStatus, ExecutionStatus, GateDecision
from app.services.gate.policy import GateInput, apply_gate_policy


def check(
    code="C",
    critical=True,
    status=CheckStatus.PASS,
    execution=ExecutionStatus.COMPLETED,
    blocking=BlockingBehavior.NON_BLOCKING,
) -> GateInput:
    return GateInput(
        check_code=code,
        critical=critical,
        status=status.value,
        execution_status=execution.value,
        blocking_behavior=blocking.value,
    )


def test_all_critical_pass_is_approved():
    outcome = apply_gate_policy([check("A"), check("B"), check("C", critical=False)])
    assert outcome.decision == GateDecision.APPROVED


def test_critical_fail_holds():
    outcome = apply_gate_policy([check("A"), check("B", status=CheckStatus.FAIL)])
    assert outcome.decision == GateDecision.HOLD
    assert outcome.triggering_checks == ["B"]


def test_critical_uncertain_routes_to_human_review():
    outcome = apply_gate_policy([check("A"), check("B", status=CheckStatus.UNCERTAIN)])
    assert outcome.decision == GateDecision.HUMAN_REVIEW
    assert outcome.triggering_checks == ["B"]


def test_non_critical_failure_does_not_block():
    outcome = apply_gate_policy(
        [
            check("A"),
            check("DEAD_AIR", critical=False, status=CheckStatus.FAIL),
            check("RAPPORT", critical=False, status=CheckStatus.UNCERTAIN),
        ]
    )
    assert outcome.decision == GateDecision.APPROVED


def test_non_critical_failure_blocks_when_explicitly_configured():
    outcome = apply_gate_policy(
        [
            check("A"),
            check("X", critical=False, status=CheckStatus.FAIL, blocking=BlockingBehavior.BLOCKING),
        ]
    )
    assert outcome.decision == GateDecision.HOLD


@pytest.mark.parametrize("execution", [ExecutionStatus.INCOMPLETE, ExecutionStatus.ERROR])
def test_incomplete_execution_can_never_approve(execution):
    outcome = apply_gate_policy([check("A"), check("B", execution=execution)])
    assert outcome.decision == GateDecision.HUMAN_REVIEW


def test_incomplete_execution_outranks_a_critical_fail():
    """The system does not get to assert *why* a sale is stopped if it did
    not finish looking."""
    outcome = apply_gate_policy(
        [
            check("FAILED", status=CheckStatus.FAIL),
            check("BROKEN", execution=ExecutionStatus.ERROR),
        ]
    )
    assert outcome.decision == GateDecision.HUMAN_REVIEW


def test_not_applicable_checks_are_excluded_from_the_gate():
    outcome = apply_gate_policy(
        [check("A"), check("MIRN", status=CheckStatus.NOT_APPLICABLE)]
    )
    assert outcome.decision == GateDecision.APPROVED


def test_not_applicable_check_with_failed_execution_does_not_escalate():
    outcome = apply_gate_policy(
        [
            check("A"),
            check("SKIPPED", status=CheckStatus.NOT_APPLICABLE, execution=ExecutionStatus.INCOMPLETE),
        ]
    )
    assert outcome.decision == GateDecision.APPROVED


def test_no_applicable_checks_is_not_an_approval():
    outcome = apply_gate_policy([check("A", status=CheckStatus.NOT_APPLICABLE)])
    assert outcome.decision == GateDecision.HUMAN_REVIEW
