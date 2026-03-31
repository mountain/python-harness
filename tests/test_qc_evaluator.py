"""
Tests for governance QC evaluation logic.
"""

from typing import Any

from python_harness.qc_evaluator import QCEvaluator


def test_qc_evaluator_checks_return_success() -> None:
    """
    Test that individual QC checks return successful empty failures.
    """
    evaluator = QCEvaluator(".")

    invariants = evaluator.check_hard_invariants()
    obligations = evaluator.check_obligations()
    self_touch = evaluator.check_self_touch()

    assert invariants == {"status": "success", "failures": []}
    assert obligations == {"status": "success", "failures": []}
    assert self_touch == {"status": "success", "failures": []}


def test_qc_evaluate_aggregates_failures(monkeypatch: Any) -> None:
    """
    Test that evaluate aggregates failures from all QC checks.
    """
    monkeypatch.setattr(
        QCEvaluator,
        "check_hard_invariants",
        lambda self: {"status": "failed", "failures": ["invariant failed"]},
    )
    monkeypatch.setattr(
        QCEvaluator,
        "check_obligations",
        lambda self: {"status": "failed", "failures": ["obligation failed"]},
    )
    monkeypatch.setattr(
        QCEvaluator,
        "check_self_touch",
        lambda self: {"status": "failed", "failures": ["self-touch failed"]},
    )

    evaluator = QCEvaluator(".")
    result = evaluator.evaluate()

    assert result["all_passed"] is False
    assert result["failures"] == [
        "invariant failed",
        "obligation failed",
        "self-touch failed",
    ]


def test_qc_evaluate_passes_when_no_failures() -> None:
    """
    Test that evaluate passes when all QC checks succeed.
    """
    evaluator = QCEvaluator(".")

    result = evaluator.evaluate()

    assert result["all_passed"] is True
    assert result["failures"] == []
