from collections.abc import Callable
from pathlib import Path
from typing import Any

from python_harness.refine_apply import NullSuggestionApplier
from python_harness.refine_execution import execute_candidate
from python_harness.refine_models import (
    Candidate,
    RefineRoundResult,
    SuggestionApplier,
)
from python_harness.refine_round_evaluation import (
    emit_progress,
    suggestions_from,
)
from python_harness.refine_scoring import select_best_candidate

EvaluatorRunner = Callable[[Path], dict[str, Any]]


def _evaluate_candidate(
    *,
    path: Path,
    label: str,
    evaluator_runner: EvaluatorRunner,
    progress_callback: Any,
) -> dict[str, Any]:
    emit_progress(progress_callback, f"{label} guardrail 2 measure started")
    result: dict[str, Any] = evaluator_runner(path)
    emit_progress(progress_callback, f"{label} guardrail 2 completed")
    return result


def _execute_candidate_layer(
    *,
    parent: Candidate,
    suggestions: list[dict[str, str]],
    candidate_prefix: str,
    workspace_root: Path,
    applier: SuggestionApplier,
    self_check_runner: Any,
    evaluator_runner: EvaluatorRunner,
    max_retries: int,
    round_result: RefineRoundResult,
    progress_callback: Any,
    completed_candidates: int,
    discovered_candidates: int,
) -> tuple[int, int]:
    for index, suggestion in enumerate(suggestions, start=1):
        candidate_id = f"{candidate_prefix}{index}"
        emit_progress(
            progress_callback,
            f"candidate {completed_candidates + 1}/{discovered_candidates} started: "
            f"{candidate_id}",
        )
        candidate = execute_candidate(
            parent=parent,
            candidate_id=candidate_id,
            suggestion=suggestion,
            workspace_root=workspace_root,
            applier=applier,
            self_check_runner=self_check_runner,
            evaluator_runner=lambda path, label=candidate_id: _evaluate_candidate(
                path=path,
                label=label,
                evaluator_runner=evaluator_runner,
                progress_callback=progress_callback,
            ),
            max_retries=max_retries,
            progress_callback=progress_callback,
        )
        completed_candidates += 1
        emit_progress(
            progress_callback,
            f"candidate {completed_candidates}/{discovered_candidates} completed: "
            f"{candidate.id} ({candidate.status})",
        )
        round_result.candidates.append(candidate)
        if candidate.status == "measured" and candidate.evaluation:
            discovered_candidates += len(suggestions_from(candidate.evaluation))
    return completed_candidates, discovered_candidates


def run_refine_round(
    *,
    target_path: Path,
    workspace_root: Path,
    evaluator_runner: EvaluatorRunner,
    applier: SuggestionApplier,
    self_check_runner: Any,
    max_retries: int,
    progress_callback: Any = None,
    baseline_evaluator_runner: EvaluatorRunner | None = None,
) -> RefineRoundResult:
    emit_progress(progress_callback, "baseline measure started")
    baseline_runner = baseline_evaluator_runner or evaluator_runner
    baseline = Candidate(
        id="baseline",
        parent_id=None,
        depth=0,
        workspace=target_path,
        suggestion_trace=(),
        evaluation=dict(baseline_runner(target_path)),
        status="measured",
    )
    emit_progress(progress_callback, "baseline measure passed")
    round_result = RefineRoundResult(baseline=baseline)
    baseline_suggestions = suggestions_from(baseline.evaluation)

    if isinstance(applier, NullSuggestionApplier) and baseline_suggestions:
        round_result.winner = baseline
        round_result.stop_reason = "no suggestion applier configured"
        return round_result

    first_layer: list[Candidate] = []
    completed_candidates = 0
    discovered_candidates = len(baseline_suggestions)
    completed_candidates, discovered_candidates = _execute_candidate_layer(
        parent=baseline,
        suggestions=baseline_suggestions,
        candidate_prefix="l1-",
        workspace_root=workspace_root,
        applier=applier,
        self_check_runner=self_check_runner,
        evaluator_runner=evaluator_runner,
        max_retries=max_retries,
        round_result=round_result,
        progress_callback=progress_callback,
        completed_candidates=completed_candidates,
        discovered_candidates=discovered_candidates,
    )
    first_layer.extend(
        candidate for candidate in round_result.candidates if candidate.depth == 1
    )

    for parent in first_layer:
        if parent.status != "measured" or not parent.evaluation:
            continue
        completed_candidates, discovered_candidates = _execute_candidate_layer(
            parent=parent,
            suggestions=suggestions_from(parent.evaluation),
            candidate_prefix=f"{parent.id}-l2-",
            workspace_root=workspace_root,
            applier=applier,
            self_check_runner=self_check_runner,
            evaluator_runner=evaluator_runner,
            max_retries=max_retries,
            round_result=round_result,
            progress_callback=progress_callback,
            completed_candidates=completed_candidates,
            discovered_candidates=discovered_candidates,
        )

    selection = select_best_candidate([baseline, *round_result.candidates])
    round_result.winner = selection.winner
    round_result.stop_reason = selection.reason
    return round_result
