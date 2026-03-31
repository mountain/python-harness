from typing import Any

from python_harness.soft_eval_report_metrics import determine_verdict


def build_mock_summary(
    metrics: dict[str, Any],
    hard_results: dict[str, Any],
) -> str:
    summary_parts = []
    if metrics["hard_failed"]:
        pytest_err = hard_results.get("pytest", {}).get("error_message", "")
        summary_parts.append(f"Hard evaluation failed. {pytest_err}".strip())
    if metrics["qc_failed"]:
        summary_parts.append("Governance QC failed.")
    if not summary_parts:
        summary_parts.append("Mock evaluation completed without LLM.")
    return " ".join(summary_parts)


def build_mock_final_report(
    hard_results: dict[str, Any],
    metrics: dict[str, Any],
) -> dict[str, Any]:
    return {
        "verdict": determine_verdict(metrics, mock=True),
        "summary": build_mock_summary(metrics, hard_results),
        "suggestions": [
            {
                "title": "Mock Suggestion 1",
                "description": "Add more docstrings.",
                "target_file": "all",
            },
            {
                "title": "Mock Suggestion 2",
                "description": "Refactor large functions.",
                "target_file": "all",
            },
            {
                "title": "Mock Suggestion 3",
                "description": "Improve test coverage.",
                "target_file": "tests/",
            },
        ],
    }
