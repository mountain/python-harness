"""
Tests for hard evaluation logic.
"""

import json
from pathlib import Path
from typing import Any

from python_harness.hard_evaluator import HardEvaluator


def test_hard_evaluator_methods(monkeypatch: Any) -> None:
    """
    Test methods of HardEvaluator.
    """
    def mock_run_pytest(self: HardEvaluator) -> dict[str, Any]:
        return {"status": "success", "output": "{}", "return_code": 0}

    monkeypatch.setattr(HardEvaluator, "run_pytest", mock_run_pytest)

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
        # Check if the command is for radon cc (sys.executable, -m, radon, cc)
        if (
            args
            and len(args) >= 4
            and args[1] == "-m"
            and args[2] == "radon"
            and args[3] == "cc"
        ):
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


def test_run_pytest_times_out(monkeypatch: Any) -> None:
    """
    Test that run_pytest fails cleanly when the subprocess times out.
    """
    import subprocess

    captured: dict[str, Any] = {}

    def mock_run(args: Any, **kwargs: Any) -> Any:
        captured["timeout"] = kwargs.get("timeout")
        raise subprocess.TimeoutExpired(cmd=args, timeout=kwargs["timeout"])

    monkeypatch.setattr("subprocess.run", mock_run)

    evaluator = HardEvaluator(".")
    result = evaluator.run_pytest()

    assert captured["timeout"] == 60
    assert result["status"] == "failed"
    assert "timed out after 60 seconds" in result["error_message"]


def test_cli_measure_is_below_complexity_threshold() -> None:
    """
    Test that the CLI measure command stays below the Radon CC threshold.
    """
    evaluator = HardEvaluator("python_harness/cli.py")

    result = evaluator.run_radon_cc()

    measure_issues = [
        issue
        for issue in result.get("issues", [])
        if issue["name"] == "measure" and issue["file"].endswith("cli.py")
    ]
    assert measure_issues == []


def test_soft_generate_final_report_is_below_complexity_threshold() -> None:
    """
    Test that soft_evaluator.generate_final_report stays below the CC threshold.
    """
    evaluator = HardEvaluator("python_harness/soft_evaluator.py")

    result = evaluator.run_radon_cc()

    report_issues = [
        issue
        for issue in result.get("issues", [])
        if issue["name"] == "generate_final_report"
        and issue["file"].endswith("soft_evaluator.py")
    ]
    assert report_issues == []


def test_run_pytest_reads_coverage_percentage(
    monkeypatch: Any,
    tmp_path: Path,
) -> None:
    """
    Test that run_pytest extracts coverage percentage from the JSON report file.
    """
    def mock_run(args: Any, **kwargs: Any) -> Any:
        coverage_arg = next(
            arg
            for arg in args
            if isinstance(arg, str) and arg.startswith("--cov-report=json:")
        )
        coverage_path = coverage_arg.split(":", maxsplit=1)[1]
        Path(coverage_path).write_text(
            json.dumps({"totals": {"percent_covered": 63.0}})
        )

        class MockResult:
            returncode = 0
            stdout = "pytest output"
            stderr = ""

        return MockResult()

    monkeypatch.setattr("subprocess.run", mock_run)

    evaluator = HardEvaluator(str(tmp_path))
    result = evaluator.run_pytest()

    assert result["status"] == "success"
    assert result["coverage_percentage"] == 63.0


def test_evaluate_fails_when_coverage_below_threshold(monkeypatch: Any) -> None:
    """
    Test that successful tests still fail the hard gate when coverage is too low.
    """
    monkeypatch.setattr(
        HardEvaluator,
        "run_ruff",
        lambda self: {"status": "success", "issues": [], "return_code": 0},
    )
    monkeypatch.setattr(
        HardEvaluator,
        "run_mypy",
        lambda self: {"status": "success", "output": "", "return_code": 0},
    )
    monkeypatch.setattr(
        HardEvaluator,
        "run_ty",
        lambda self: {"status": "warning", "error_message": "ty not found"},
    )
    monkeypatch.setattr(
        HardEvaluator,
        "run_radon_cc",
        lambda self: {"status": "success", "issues": [], "return_code": 0},
    )
    monkeypatch.setattr(
        HardEvaluator,
        "run_radon_mi",
        lambda self: {"status": "success", "mi_scores": {}},
    )
    monkeypatch.setattr(
        HardEvaluator,
        "run_pytest",
        lambda self: {
            "status": "success",
            "output": "pytest output",
            "return_code": 0,
            "coverage_percentage": 63.0,
        },
    )

    evaluator = HardEvaluator(".")
    result = evaluator.evaluate()

    assert result["all_passed"] is False
    assert result["pytest"]["status"] == "failed"
    assert "63.00%" in result["pytest"]["error_message"]


def test_run_ruff_parses_json_output(monkeypatch: Any) -> None:
    """
    Test that run_ruff parses JSON issues from subprocess output.
    """
    def mock_run(args: Any, **kwargs: Any) -> Any:
        class MockResult:
            returncode = 1
            stdout = json.dumps([{"filename": "a.py", "message": "boom"}])
            stderr = ""

        return MockResult()

    monkeypatch.setattr("subprocess.run", mock_run)

    evaluator = HardEvaluator(".")
    result = evaluator.run_ruff()

    assert result["status"] == "failed"
    assert result["issues"][0]["filename"] == "a.py"


def test_run_mypy_returns_stdout(monkeypatch: Any) -> None:
    """
    Test that run_mypy returns stdout on failure.
    """
    def mock_run(args: Any, **kwargs: Any) -> Any:
        class MockResult:
            returncode = 1
            stdout = "a.py:1: error: nope"
            stderr = ""

        return MockResult()

    monkeypatch.setattr("subprocess.run", mock_run)

    evaluator = HardEvaluator(".")
    result = evaluator.run_mypy()

    assert result["status"] == "failed"
    assert "error: nope" in result["output"]


def test_run_radon_mi_reads_scores(monkeypatch: Any) -> None:
    """
    Test that run_radon_mi parses maintainability scores from JSON.
    """
    def mock_run(args: Any, **kwargs: Any) -> Any:
        class MockResult:
            returncode = 0
            stdout = json.dumps({"a.py": {"mi": 77.0}})
            stderr = ""

        return MockResult()

    monkeypatch.setattr("subprocess.run", mock_run)

    evaluator = HardEvaluator(".")
    result = evaluator.run_radon_mi()

    assert result["status"] == "success"
    assert result["mi_scores"] == {"a.py": 77.0}


def test_evaluate_fails_when_coverage_report_missing(monkeypatch: Any) -> None:
    """
    Test that missing coverage data fails the hard gate even when tests pass.
    """
    monkeypatch.setattr(
        HardEvaluator,
        "run_ruff",
        lambda self: {"status": "success", "issues": [], "return_code": 0},
    )
    monkeypatch.setattr(
        HardEvaluator,
        "run_mypy",
        lambda self: {"status": "success", "output": "", "return_code": 0},
    )
    monkeypatch.setattr(
        HardEvaluator,
        "run_ty",
        lambda self: {"status": "warning", "error_message": "ty not found"},
    )
    monkeypatch.setattr(
        HardEvaluator,
        "run_radon_cc",
        lambda self: {"status": "success", "issues": [], "return_code": 0},
    )
    monkeypatch.setattr(
        HardEvaluator,
        "run_radon_mi",
        lambda self: {"status": "success", "mi_scores": {}},
    )
    monkeypatch.setattr(
        HardEvaluator,
        "run_pytest",
        lambda self: {
            "status": "success",
            "output": "pytest output",
            "return_code": 0,
            "coverage_percentage": None,
        },
    )

    evaluator = HardEvaluator(".")
    result = evaluator.evaluate()

    assert result["all_passed"] is False
    assert (
        result["pytest"]["error_message"]
        == "Coverage report was missing or unreadable."
    )
