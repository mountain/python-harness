from typing import Any

from python_harness.soft_eval_report_shared import MI_PASS_THRESHOLD, QA_PASS_THRESHOLD


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
