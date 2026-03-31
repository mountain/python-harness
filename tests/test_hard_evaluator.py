"""
Tests for hard evaluation logic.
"""

from python_harness.hard_evaluator import HardEvaluator


def test_hard_evaluator_methods() -> None:
    """
    Test methods of HardEvaluator.
    """
    evaluator = HardEvaluator(".")
    
    ruff_result = evaluator.run_ruff()
    assert "status" in ruff_result
    
    mypy_result = evaluator.run_mypy()
    assert "status" in mypy_result
    
    ty_result = evaluator.run_ty()
    assert "status" in ty_result

    # pytest_result = evaluator.run_pytest() # Causes infinite loop when run in test
    # assert "status" in pytest_result
    
    eval_result = evaluator.evaluate()
    assert "ruff" in eval_result
    assert "mypy" in eval_result
    assert "ty" in eval_result
