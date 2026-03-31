"""
Tests for overall evaluation orchestration.
"""

from python_harness.evaluator import Evaluator


def test_evaluator_methods() -> None:
    """
    Test main evaluator orchestration.
    """
    evaluator = Evaluator(".")
    
    result = evaluator.run()
    assert "overall_status" in result
    assert "hard_evaluation" in result
    assert "qc_evaluation" in result
    assert "soft_evaluation" in result
