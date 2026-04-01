"""
Result post-processing for hard evaluation runs.
"""

from typing import Any

PYTEST_COVERAGE_THRESHOLD = 90.0


def apply_pytest_coverage_gate(pytest_result: dict[str, Any]) -> dict[str, Any]:
    """
    Fail successful pytest runs when coverage data is missing or below threshold.
    """
    gated_result = dict(pytest_result)
    coverage_percentage = gated_result.get("coverage_percentage")

    if gated_result.get("status") != "success":
        return gated_result

    if isinstance(coverage_percentage, (int, float)):
        if coverage_percentage < PYTEST_COVERAGE_THRESHOLD:
            gated_result["status"] = "failed"
            gated_result["error_message"] = (
                f"Test coverage is {coverage_percentage:.2f}%, "
                f"which is below the {PYTEST_COVERAGE_THRESHOLD:.0f}% threshold."
            )
        return gated_result

    gated_result["status"] = "failed"
    gated_result["error_message"] = "Coverage report was missing or unreadable."
    return gated_result


def compute_all_passed(
    *,
    ruff_result: dict[str, Any],
    mypy_result: dict[str, Any],
    ty_result: dict[str, Any],
    radon_cc_result: dict[str, Any],
    pytest_result: dict[str, Any],
) -> bool:
    """
    Compute the overall hard evaluation status.
    """
    return (
        ruff_result.get("status") == "success"
        and mypy_result.get("status") == "success"
        and ty_result.get("status") in ("success", "warning")
        and radon_cc_result.get("status") in ("success", "warning")
        and pytest_result.get("status") == "success"
    )
