"""
Report-building helpers for soft evaluation.
"""

import json
from typing import Any

MI_PASS_THRESHOLD = 70.0
QA_PASS_THRESHOLD = 75.0


def collect_hard_errors(hard_results: dict[str, Any]) -> list[str]:
    if hard_results.get("all_passed", True):
        return []

    hard_errors = []
    if hard_results.get("ruff", {}).get("status") != "success":
        hard_errors.append("Linter (Ruff) failed.")
    if hard_results.get("mypy", {}).get("status") != "success":
        hard_errors.append("Type checker (Mypy) failed.")
    if hard_results.get("pytest", {}).get("status") != "success":
        hard_errors.append(
            hard_results.get("pytest", {}).get(
                "error_message",
                "Tests or Coverage failed.",
            )
        )
    return hard_errors


def extract_metrics(
    hard_results: dict[str, Any],
    qc_results: dict[str, Any],
    soft_results: dict[str, Any],
) -> dict[str, Any]:
    mi_scores = hard_results.get("radon_mi", {}).get("mi_scores", {})
    avg_mi = sum(mi_scores.values()) / len(mi_scores) if mi_scores else 100.0
    return {
        "avg_mi": avg_mi,
        "cc_issues": hard_results.get("radon_cc", {}).get("issues", []),
        "hard_errors": collect_hard_errors(hard_results),
        "hard_failed": not hard_results.get("all_passed", True),
        "qa_entities": soft_results.get("qa_results", {}).get("sampled_entities", []),
        "qa_score": soft_results.get("understandability_score", 100.0),
        "qc_errors": qc_results.get("failures", []),
        "qc_failed": not qc_results.get("all_passed", True),
    }


def determine_verdict(metrics: dict[str, Any], mock: bool = False) -> str:
    suffix = " (Mock)" if mock else ""
    if metrics["hard_failed"] or metrics["qc_failed"]:
        return f"Fail{suffix}"
    passed = (
        metrics["avg_mi"] >= MI_PASS_THRESHOLD
        and metrics["qa_score"] > QA_PASS_THRESHOLD
        and not metrics["cc_issues"]
    )
    return f"Pass{suffix}" if passed else f"Fail{suffix}"


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


def build_final_report_messages(metrics: dict[str, Any]) -> list[dict[str, str]]:
    sys_prompt = (
        "You are an elite Python Codebase Evaluator. You have just analyzed "
        "a repository. Your task is to provide a final judgment and EXACTLY "
        "3 concrete, actionable improvement suggestions.\n"
        "If the codebase failed its Hard or QC evaluations (e.g. tests "
        "failed, coverage is low, or governance violated), your suggestions "
        "MUST prioritize fixing those issues.\n"
        "Otherwise, focus on refactoring/quality improvements without "
        "changing external functionality.\n\n"
        "Output MUST be in valid JSON matching this schema:\n"
        "{\n"
        '  "verdict": "Pass" or "Fail",\n'
        '  "summary": "One paragraph summary of codebase health and '
        'any critical failures",\n'
        '  "suggestions": [\n'
        '    {"title": "str", "description": "str", "target_file": "str"}\n'
        "  ]\n"
        "}\n"
        "Rule for Verdict: If there are Hard Failures or QC Failures, "
        "verdict MUST be Fail. Otherwise, Pass if Average Maintainability "
        f">= {MI_PASS_THRESHOLD:.0f} and QA Score > {QA_PASS_THRESHOLD:.0f} "
        "and no Critical CC issues (>15). Otherwise Fail."
    )
    user_content = (
        f"Metrics:\n"
        f"- Average Maintainability Index (MI): {metrics['avg_mi']:.1f}/100\n"
        f"- Number of functions with Cyclomatic Complexity > 15: "
        f"{len(metrics['cc_issues'])}\n"
        f"- Agent QA Readability Score: {metrics['qa_score']:.1f}/100\n\n"
        f"Failures (Prioritize these!):\n"
        f"- Hard Evaluation Errors: "
        f"{metrics['hard_errors'] if metrics['hard_errors'] else 'None'}\n"
        f"- QC/Governance Errors: "
        f"{metrics['qc_errors'] if metrics['qc_errors'] else 'None'}\n\n"
        f"QA Feedback Snippets:\n"
        + "\n".join(
            [f"  * {q['entity']}: {q['feedback']}" for q in metrics["qa_entities"]]
        )
    )
    return [
        {"role": "system", "content": sys_prompt},
        {"role": "user", "content": user_content},
    ]


def parse_final_report_response(raw_content: str) -> dict[str, Any]:
    parsed_json = json.loads(raw_content)
    if isinstance(parsed_json, dict):
        return parsed_json
    raise ValueError("JSON response is not a dictionary.")
