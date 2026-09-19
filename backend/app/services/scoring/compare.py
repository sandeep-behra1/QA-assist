"""Compare two scoring runs of the same sale.

Runs are immutable, so "what changed after we fixed the data?" is answered by
diffing two rows that both still exist -- not by remembering what the last
result used to be.
"""

from __future__ import annotations

from app.models import ScoringRun


class RunComparisonError(ValueError):
    pass


def compare_runs(base: ScoringRun, target: ScoringRun) -> dict:
    if base.lead_id != target.lead_id:
        raise RunComparisonError("Only two runs of the same sale can be compared.")

    before = {r.check_code: r for r in base.check_results}
    after = {r.check_code: r for r in target.check_results}

    changes = []
    unchanged = 0
    for code in sorted(set(before) | set(after), key=lambda c: (after.get(c) or before[c]).display_order):
        old, new = before.get(code), after.get(code)
        old_view = (
            (old.effective_status, old.observed_value, old.expected_value) if old else (None, None, None)
        )
        new_view = (
            (new.effective_status, new.observed_value, new.expected_value) if new else (None, None, None)
        )
        if old_view == new_view:
            unchanged += 1
            continue
        reference = new or old
        changes.append(
            {
                "check_code": code,
                "check_name": reference.check_name,
                "critical": reference.critical,
                "before_status": old_view[0],
                "after_status": new_view[0],
                "before_observed": old_view[1],
                "after_observed": new_view[1],
                "before_expected": old_view[2],
                "after_expected": new_view[2],
                "reason_after": new.reason if new else "Check no longer runs.",
            }
        )

    return {
        "lead_id": base.lead_id,
        "base_run_id": base.id,
        "target_run_id": target.id,
        "base_gate": base.effective_gate_result,
        "target_gate": target.effective_gate_result,
        "gate_changed": base.effective_gate_result != target.effective_gate_result,
        "base_qa_score": base.qa_score_weighted,
        "target_qa_score": target.qa_score_weighted,
        "base_checklist_version_id": base.checklist_version_id,
        "target_checklist_version_id": target.checklist_version_id,
        "changes": changes,
        "unchanged_count": unchanged,
    }
