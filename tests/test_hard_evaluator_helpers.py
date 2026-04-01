"""
Tests for hard evaluator helper modules.
"""

from python_harness.hard_eval_helpers import (
    apply_pytest_coverage_gate,
    compute_all_passed,
    parse_radon_cc_issues,
    parse_radon_mi_scores,
)


def test_apply_pytest_coverage_gate_fails_below_threshold() -> None:
    """
    Coverage below the threshold should fail an otherwise successful pytest run.
    """
    pytest_result = {
        "status": "success",
        "output": "pytest output",
        "return_code": 0,
        "coverage_percentage": 63.0,
    }

    gated = apply_pytest_coverage_gate(pytest_result)

    assert gated["status"] == "failed"
    assert "63.00%" in gated["error_message"]


def test_apply_pytest_coverage_gate_fails_missing_report() -> None:
    """
    Missing coverage data should fail an otherwise successful pytest run.
    """
    pytest_result = {
        "status": "success",
        "output": "pytest output",
        "return_code": 0,
        "coverage_percentage": None,
    }

    gated = apply_pytest_coverage_gate(pytest_result)

    assert gated["status"] == "failed"
    assert gated["error_message"] == "Coverage report was missing or unreadable."


def test_compute_all_passed_allows_warning_only_tools() -> None:
    """
    ty and radon warnings should not fail the overall hard evaluation.
    """
    result = compute_all_passed(
        ruff_result={"status": "success"},
        mypy_result={"status": "success"},
        ty_result={"status": "warning"},
        radon_cc_result={"status": "warning"},
        pytest_result={"status": "success"},
    )

    assert result is True


def test_parse_radon_cc_issues_returns_only_high_complexity_blocks() -> None:
    """
    Only functions above the CC threshold should be returned as issues.
    """
    issues = parse_radon_cc_issues(
        {
            "pkg/module.py": [
                {"name": "small", "type": "function", "complexity": 3},
                {"name": "large", "type": "function", "complexity": 16},
            ]
        }
    )

    assert issues == [
        {
            "file": "pkg/module.py",
            "name": "large",
            "type": "function",
            "complexity": 16,
        }
    ]


def test_parse_radon_mi_scores_defaults_missing_scores() -> None:
    """
    Missing MI values should default to 100.0 for compatibility.
    """
    scores = parse_radon_mi_scores(
        {
            "pkg/a.py": {"mi": 77.0},
            "pkg/b.py": {},
        }
    )

    assert scores == {"pkg/a.py": 77.0, "pkg/b.py": 100.0}
