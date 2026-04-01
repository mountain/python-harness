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
                "title": "Narrow CLI status formatting",
                "description": (
                    "Make one small readability fix without changing behavior."
                ),
                "target_file": "python_harness/cli.py",
            },
            {
                "title": "Tighten refine scoring helper typing",
                "description": "Apply one local typing or naming cleanup.",
                "target_file": "python_harness/refine_scoring.py",
            },
            {
                "title": "Add one focused retry regression test",
                "description": "Improve a single refine retry regression scenario.",
                "target_file": "tests/test_refine_engine.py",
            },
        ],
    }
