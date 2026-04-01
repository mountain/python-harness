from pathlib import Path
from typing import Any

from python_harness.refine_apply import (
    LLMSuggestionApplier,
    NullSuggestionApplier,
)
from python_harness.refine_round_evaluation import (
    default_evaluator_runner,
    emit_progress,
    suggestions_from,
)
from python_harness.refine_round_flow import run_refine_round
from python_harness.refine_round_paths import (
    default_workspace_root,
    validate_workspace_root,
)
from python_harness.refine_round_support import (
    determine_stop_reason,
    emit_round_summary,
    emit_stop_reason,
    persist_round,
    resolve_self_check_runner,
    resolve_suggestion_applier,
    round_scorecards,
    winner_reason,
)
from python_harness.refine_scoring import build_candidate_rank
from python_harness.refine_workspace import adopt_candidate_workspace


def run_refine(
    *,
    target_path: Path,
    workspace_root: Path | None = None,
    max_retries: int,
    loop: bool,
    max_rounds: int,
    evaluator_runner: Any | None = None,
    applier: Any | None = None,
    self_check_runner: Any | None = None,
    progress_callback: Any = None,
    default_evaluator_runner_fn: Any = default_evaluator_runner,
    run_refine_round_fn: Any = run_refine_round,
    default_workspace_root_fn: Any = default_workspace_root,
    validate_workspace_root_fn: Any = validate_workspace_root,
    resolve_suggestion_applier_fn: Any = resolve_suggestion_applier,
    resolve_self_check_runner_fn: Any = resolve_self_check_runner,
    llm_applier_factory: Any = LLMSuggestionApplier,
    null_applier_factory: Any = NullSuggestionApplier,
) -> dict[str, Any]:
    target_path = target_path.resolve()
    evaluator = evaluator_runner or default_evaluator_runner_fn
    suggestion_applier = resolve_suggestion_applier_fn(
        applier,
        llm_applier_factory=llm_applier_factory,
        null_applier_factory=null_applier_factory,
    )
    self_check = resolve_self_check_runner_fn(self_check_runner)
    resolved_workspace_root = (
        workspace_root.resolve()
        if workspace_root is not None
        else default_workspace_root_fn(target_path)
    )
    validate_workspace_root_fn(target_path, resolved_workspace_root)
    rounds_completed = 0
    winner_id = "baseline"
    stop_reason = "max rounds reached"

    while rounds_completed < max_rounds:
        emit_progress(progress_callback, f"round {rounds_completed + 1} started")
        round_result = run_refine_round_fn(
            target_path=target_path,
            workspace_root=resolved_workspace_root,
            evaluator_runner=evaluator,
            applier=suggestion_applier,
            self_check_runner=self_check,
            max_retries=max_retries,
            progress_callback=progress_callback,
        )
        rounds_completed += 1
        winner = round_result.winner or round_result.baseline
        winner_id = winner.id
        scorecards = round_scorecards(round_result)
        winner_summary = winner_reason(winner, round_result.baseline)
        emit_round_summary(
            rounds_completed,
            round_result,
            winner,
            scorecards,
            winner_summary,
            progress_callback,
        )
        baseline_rank = build_candidate_rank(round_result.baseline)
        winner_rank = build_candidate_rank(winner)
        suggestions = suggestions_from(winner.evaluation)

        if winner.workspace != target_path:
            adopt_candidate_workspace(winner.workspace, target_path)
            emit_progress(
                progress_callback,
                f"round {rounds_completed} adopted winner workspace: {winner.id}",
            )

        stop_reason = determine_stop_reason(
            round_result=round_result,
            loop=loop,
            suggestions=suggestions,
            winner_rank=winner_rank,
            baseline_rank=baseline_rank,
        )
        emit_stop_reason(rounds_completed, stop_reason, progress_callback)
        persist_round(
            workspace_root=resolved_workspace_root,
            round_number=rounds_completed,
            round_result=round_result,
            stop_reason=stop_reason,
            winner_summary=winner_summary,
            scorecards=scorecards,
        )
        if stop_reason != "max rounds reached":
            break

    return {
        "rounds_completed": rounds_completed,
        "winner_id": winner_id,
        "stop_reason": stop_reason,
    }
