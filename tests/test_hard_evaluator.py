"""
Tests for hard evaluation logic.
"""

from pathlib import Path
from typing import Any

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

def test_ty_fallback_behavior(monkeypatch: Any) -> None:
    """
    Test that run_ty gracefully falls back to a warning when 'ty' is not installed.
    """
    # Create a mock subprocess.run that always raises FileNotFoundError
    # to simulate 'ty' not being on the system PATH
    def mock_run(*args: Any, **kwargs: Any) -> Any:
        raise FileNotFoundError("[Errno 2] No such file or directory: 'ty'")
    
    monkeypatch.setattr("subprocess.run", mock_run)
    
    evaluator = HardEvaluator(".")
    result = evaluator.run_ty()
    
    assert result["status"] == "warning"
    assert "ty executable not found" in result["error_message"]

def test_ty_fallback_behavior_oserror(monkeypatch: Any) -> None:
    """
    Test that run_ty gracefully falls back to a warning when a generic Exception 
    containing the Errno 2 string is thrown.
    """
    def mock_run(*args: Any, **kwargs: Any) -> Any:
        raise Exception("[Errno 2] No such file or directory: 'ty'")
    
    monkeypatch.setattr("subprocess.run", mock_run)
    
    evaluator = HardEvaluator(".")
    result = evaluator.run_ty()
    
    assert result["status"] == "warning"
    assert "ty executable not found" in result["error_message"]

def test_radon_cc_syntax_error(monkeypatch: Any, tmp_path: Path) -> None:
    """
    Test that run_radon_cc correctly captures and reports stderr when radon 
    fails (e.g. due to syntax errors in the target codebase).
    """
    # Create a mock subprocess.run that simulates radon exiting with code 1
    # and writing an error to stderr (which happens when there are syntax errors)
    import subprocess
    original_run = subprocess.run
    
    def mock_run(args: Any, **kwargs: Any) -> Any:
        if args and args[0] == "radon" and args[1] == "cc":
            # Simulate radon failing on syntax error
            class MockResult:
                returncode = 1
                stdout = ""
                stderr = "ERROR: SyntaxError in bad.py"
            return MockResult()
        return original_run(args, **kwargs)
        
    monkeypatch.setattr("subprocess.run", mock_run)
    
    evaluator = HardEvaluator(str(tmp_path))
    result = evaluator.run_radon_cc()
    
    assert result["status"] == "failed"
    assert len(result.get("issues", [])) == 0
    # Radon should output to stderr because of the syntax error
    assert "SyntaxError" in result["error_message"] or result["return_code"] != 0
