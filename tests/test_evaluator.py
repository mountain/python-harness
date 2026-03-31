"""
Tests for overall evaluation orchestration.
"""

from typing import Any

from python_harness.evaluator import Evaluator


def test_evaluator_methods(monkeypatch: Any) -> None:
    """
    Test main evaluator orchestration.
    """
    monkeypatch.setattr(
        "python_harness.hard_evaluator.HardEvaluator.evaluate",
        lambda self: {"all_passed": True},
    )
    monkeypatch.setattr(
        "python_harness.qc_evaluator.QCEvaluator.evaluate",
        lambda self: {"all_passed": True, "failures": []},
    )
    monkeypatch.setattr(
        "python_harness.soft_evaluator.SoftEvaluator.evaluate",
        lambda self: {"status": "success", "understandability_score": 100.0},
    )
    monkeypatch.setattr(
        "python_harness.soft_evaluator.SoftEvaluator.generate_final_report",
        lambda self, hard_results, qc_results, soft_results: {"verdict": "Pass"},
    )

    evaluator = Evaluator(".")
    
    result = evaluator.run()
    assert "overall_status" in result
    assert "hard_evaluation" in result
    assert "qc_evaluation" in result
    assert "soft_evaluation" in result
