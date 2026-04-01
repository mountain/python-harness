from typing import Any

from python_harness.cli_hard_text import (
    CONTINUE_AFTER_QC_FAILURE,
    GOVERNANCE_QC_EXPLANATION,
    GOVERNANCE_QC_FAILED,
    GOVERNANCE_QC_HEADER,
    GOVERNANCE_QC_PASSED,
)

MI_HEALTHY_THRESHOLD = 70.0
MI_WARNING_THRESHOLD = 40.0


def _mi_scorecard_color(avg_mi: float) -> str:
    if avg_mi >= MI_HEALTHY_THRESHOLD:
        return "green"
    if avg_mi >= MI_WARNING_THRESHOLD:
        return "yellow"
    return "red"


def print_mi_scorecard(console: Any, hard_results: dict[str, Any]) -> None:
    mi_scores = hard_results.get("radon_mi", {}).get("mi_scores", {})
    if not mi_scores:
        return
    avg_mi = sum(mi_scores.values()) / len(mi_scores)
    color = _mi_scorecard_color(avg_mi)
    console.print(f"[{color}]Average Maintainability Index: {avg_mi:.1f}/100[/{color}]")


def print_qc_summary(console: Any, qc_results: dict[str, Any]) -> None:
    console.print()
    console.print(GOVERNANCE_QC_HEADER)
    if qc_results["all_passed"]:
        console.print(GOVERNANCE_QC_PASSED)
        console.print()
        return
    console.print(GOVERNANCE_QC_FAILED)
    console.print()
    console.print(GOVERNANCE_QC_EXPLANATION)
    for failure in qc_results["failures"]:
        console.print(f"[red]- {failure}[/red]")
    console.print()
    console.print(CONTINUE_AFTER_QC_FAILURE)
    console.print()
