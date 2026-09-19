"""Evaluation method -> evaluator dispatch.

Dispatch is on the *configured method*, never on retailer or check name, so
a new rule is a database row rather than a new branch in Python.
"""

from __future__ import annotations

from collections.abc import Callable

from app.core.enums import EvaluationMethod
from app.services.scoring.context import EvaluationContext, EvaluationOutcome
from app.services.scoring.evaluators import (
    evaluate_behaviour,
    evaluate_factual,
    evaluate_semantic,
    evaluate_verbatim,
)

Evaluator = Callable[[EvaluationContext], EvaluationOutcome]

EVALUATORS: dict[str, Evaluator] = {
    EvaluationMethod.EXACT_TEXT.value: evaluate_verbatim,
    EvaluationMethod.NORMALIZED_TEXT.value: evaluate_verbatim,
    EvaluationMethod.EMAIL.value: evaluate_factual,
    EvaluationMethod.NUMERIC.value: evaluate_factual,
    EvaluationMethod.DATE.value: evaluate_factual,
    EvaluationMethod.BOOLEAN.value: evaluate_factual,
    EvaluationMethod.IDENTIFIER.value: evaluate_factual,
    EvaluationMethod.SEMANTIC.value: evaluate_semantic,
    EvaluationMethod.BEHAVIOUR.value: evaluate_behaviour,
}


def get_evaluator(evaluation_method: str) -> Evaluator | None:
    return EVALUATORS.get(evaluation_method)
