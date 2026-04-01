from collections.abc import Callable
from pathlib import Path
from typing import Any

from python_harness.hard_evaluator import HardEvaluator
from python_harness.qc_evaluator import QCEvaluator
from python_harness.soft_evaluator import SoftEvaluator

EvaluatorFactory = Callable[[str], Any]


def emit_progress(progress_callback: Any, message: str) -> None:
    if progress_callback is not None:
        progress_callback(message)


def default_evaluator_runner(
    path: Path,
    progress_callback: Any = None,
    label: str = "baseline",
    *,
    hard_evaluator_factory: EvaluatorFactory = HardEvaluator,
    qc_evaluator_factory: EvaluatorFactory = QCEvaluator,
    soft_evaluator_factory: EvaluatorFactory = SoftEvaluator,
) -> dict[str, Any]:
    emit_progress(progress_callback, f"{label} guardrail 1 started")
    hard_evaluator = hard_evaluator_factory(str(path))
    hard_results = hard_evaluator.evaluate()
    if hard_results.get("all_passed", False):
        emit_progress(progress_callback, f"{label} guardrail 1 passed")
    else:
        emit_progress(progress_callback, f"{label} guardrail 1 failed")

    emit_progress(progress_callback, f"{label} guardrail 2 started")
    qc_evaluator = qc_evaluator_factory(str(path))
    qc_results = qc_evaluator.evaluate()
    if qc_results.get("all_passed", False):
        emit_progress(progress_callback, f"{label} guardrail 2 passed")
    else:
        emit_progress(progress_callback, f"{label} guardrail 2 failed")

    emit_progress(progress_callback, f"{label} soft evaluation started")
    soft_evaluator = soft_evaluator_factory(str(path))
    soft_results = soft_evaluator.evaluate()
    final_report = soft_evaluator.generate_final_report(
        hard_results,
        qc_results,
        soft_results,
    )
    emit_progress(progress_callback, f"{label} soft evaluation passed")
    return {
        "hard_evaluation": hard_results,
        "qc_evaluation": qc_results,
        "soft_evaluation": soft_results,
        "final_report": final_report,
        "overall_status": "success",
    }


def suggestions_from(evaluation: dict[str, Any] | None) -> list[dict[str, str]]:
    if not evaluation:
        return []
    final_report = evaluation.get("final_report", {})
    raw_suggestions = final_report.get("suggestions", [])
    suggestions: list[dict[str, str]] = []
    for suggestion in raw_suggestions:
        if not isinstance(suggestion, dict):
            continue
        title = str(suggestion.get("title", "")).strip()
        description = str(suggestion.get("description", "")).strip()
        target_file = str(suggestion.get("target_file", "")).strip()
        if not title or not description or not target_file:
            continue
        if target_file == "all" or target_file.endswith("/"):
            continue
        suggestions.append(
            {
                "title": title,
                "description": description,
                "target_file": target_file,
            }
        )
    return suggestions[:3]
