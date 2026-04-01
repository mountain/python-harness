from pathlib import Path
from typing import Any

from python_harness.evaluator import Evaluator
from python_harness.refine_apply import NullSuggestionApplier
from python_harness.refine_execution import execute_candidate
from python_harness.refine_models import (
    Candidate,
    RefineRoundResult,
    SuggestionApplier,
)
from python_harness.refine_scoring import build_candidate_rank, select_best_candidate
from python_harness.refine_workspace import adopt_candidate_workspace


def default_evaluator_runner(path: Path) -> dict[str, Any]:
    return Evaluator(str(path)).run()


def suggestions_from(evaluation: dict[str, Any] | None) -> list[dict[str, str]]:
    if not evaluation:
        return []
    final_report = evaluation.get("final_report", {})
    raw_suggestions = final_report.get("suggestions", [])
    return [
        suggestion
        for suggestion in raw_suggestions
        if isinstance(suggestion, dict) and "title" in suggestion
    ][:3]


def default_workspace_root(target_path: Path) -> Path:
    return target_path / ".harness-refine"


def validate_workspace_root(target_path: Path, workspace_root: Path) -> None:
    if workspace_root == target_path:
        raise ValueError("workspace_root must not be target_path itself")
    if (
        workspace_root.is_relative_to(target_path)
        and workspace_root.parent != target_path
    ):
        raise ValueError("workspace_root inside target_path must be a direct child")


def run_refine_round(
    *,
    target_path: Path,
    workspace_root: Path,
    evaluator_runner: Any,
    applier: SuggestionApplier,
    self_check_runner: Any,
    max_retries: int,
) -> RefineRoundResult:
    baseline = Candidate(
        id="baseline",
        parent_id=None,
        depth=0,
        workspace=target_path,
        suggestion_trace=(),
        evaluation=evaluator_runner(target_path),
        status="measured",
    )
    round_result = RefineRoundResult(baseline=baseline)
    if (
        isinstance(applier, NullSuggestionApplier)
        and suggestions_from(baseline.evaluation)
    ):
        round_result.winner = baseline
        round_result.stop_reason = "no suggestion applier configured"
        return round_result

    first_layer: list[Candidate] = []

    for index, suggestion in enumerate(suggestions_from(baseline.evaluation), start=1):
        candidate = execute_candidate(
            parent=baseline,
            candidate_id=f"l1-{index}",
            suggestion=suggestion,
            workspace_root=workspace_root,
            applier=applier,
            self_check_runner=self_check_runner,
            evaluator_runner=evaluator_runner,
            max_retries=max_retries,
        )
        round_result.candidates.append(candidate)
        first_layer.append(candidate)

    for parent in first_layer:
        if parent.status != "measured" or not parent.evaluation:
            continue
        for index, suggestion in enumerate(
            suggestions_from(parent.evaluation),
            start=1,
        ):
            candidate = execute_candidate(
                parent=parent,
                candidate_id=f"{parent.id}-l2-{index}",
                suggestion=suggestion,
                workspace_root=workspace_root,
                applier=applier,
                self_check_runner=self_check_runner,
                evaluator_runner=evaluator_runner,
                max_retries=max_retries,
            )
            round_result.candidates.append(candidate)

    selection = select_best_candidate([baseline, *round_result.candidates])
    round_result.winner = selection.winner
    round_result.stop_reason = selection.reason
    return round_result


def run_refine(
    *,
    target_path: Path,
    workspace_root: Path | None = None,
    max_retries: int,
    loop: bool,
    max_rounds: int,
    evaluator_runner: Any | None = None,
    applier: SuggestionApplier | None = None,
    self_check_runner: Any | None = None,
) -> dict[str, Any]:
    target_path = target_path.resolve()
    evaluator = evaluator_runner or default_evaluator_runner
    suggestion_applier = applier or NullSuggestionApplier()
    self_check = self_check_runner
    if self_check is None:
        from python_harness.refine_checks import default_self_check_runner

        self_check = default_self_check_runner
    resolved_workspace_root = (
        workspace_root.resolve()
        if workspace_root is not None
        else default_workspace_root(target_path)
    )
    validate_workspace_root(target_path, resolved_workspace_root)
    rounds_completed = 0
    winner_id = "baseline"
    stop_reason = "max rounds reached"

    while rounds_completed < max_rounds:
        round_result = run_refine_round(
            target_path=target_path,
            workspace_root=resolved_workspace_root,
            evaluator_runner=evaluator,
            applier=suggestion_applier,
            self_check_runner=self_check,
            max_retries=max_retries,
        )
        rounds_completed += 1
        winner = round_result.winner or round_result.baseline
        winner_id = winner.id

        baseline_rank = build_candidate_rank(round_result.baseline)
        winner_rank = build_candidate_rank(winner)
        suggestions = suggestions_from(winner.evaluation)

        if round_result.stop_reason == "no suggestion applier configured":
            stop_reason = round_result.stop_reason
            break

        if winner.workspace != target_path:
            adopt_candidate_workspace(winner.workspace, target_path)

        if not loop:
            stop_reason = "single round completed"
            break
        if not suggestions:
            stop_reason = "winner has no suggestions"
            break
        if winner_rank <= baseline_rank:
            stop_reason = "winner did not improve baseline"
            break

    return {
        "rounds_completed": rounds_completed,
        "winner_id": winner_id,
        "stop_reason": stop_reason,
    }
