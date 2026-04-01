from pathlib import Path
from typing import Any

from python_harness.refine_models import Candidate, SuggestionApplier
from python_harness.refine_workspace import create_candidate_workspace


def _emit(progress_callback: Any, message: str) -> None:
    if progress_callback is not None:
        progress_callback(message)


def execute_candidate(
    *,
    parent: Candidate,
    candidate_id: str,
    suggestion: dict[str, str],
    workspace_root: Path,
    applier: SuggestionApplier,
    self_check_runner: Any,
    evaluator_runner: Any,
    max_retries: int,
    progress_callback: Any = None,
) -> Candidate:
    workspace = create_candidate_workspace(
        parent.workspace,
        workspace_root,
        candidate_id,
    )
    feedback = ""
    retries = 0
    suggestion_title = suggestion.get("title", candidate_id)

    while True:
        apply_result: dict[str, Any] | None = None
        _emit(
            progress_callback,
            f"{candidate_id} apply started: {suggestion_title}",
        )
        try:
            apply_result = applier.apply(
                workspace,
                suggestion,
                failure_feedback=feedback,
            )
            if not bool(apply_result.get("ok", False)):
                feedback = str(
                    apply_result.get("failure_reason") or "suggestion apply failed"
                )
                raise RuntimeError(feedback)
            _emit(progress_callback, f"{candidate_id} apply passed")
        except Exception as exc:
            feedback = str(exc)
            retryable = True
            if apply_result is not None:
                retryable = bool(apply_result.get("retryable", True))
            _emit(progress_callback, f"{candidate_id} apply failed: {feedback}")
            if not retryable:
                return Candidate(
                    id=candidate_id,
                    parent_id=parent.id,
                    depth=parent.depth + 1,
                    workspace=workspace,
                    suggestion_trace=parent.suggestion_trace + (suggestion_title,),
                    status="failed",
                    retry_count=retries,
                    selection_reason=feedback,
                )
            retries += 1
            if retries > max_retries:
                return Candidate(
                    id=candidate_id,
                    parent_id=parent.id,
                    depth=parent.depth + 1,
                    workspace=workspace,
                    suggestion_trace=parent.suggestion_trace + (suggestion_title,),
                    status="failed",
                    retry_count=retries - 1,
                    selection_reason=feedback,
                )
            continue

        _emit(progress_callback, f"{candidate_id} guardrail 1 started")
        is_ok, feedback = self_check_runner(workspace)
        if is_ok:
            _emit(progress_callback, f"{candidate_id} guardrail 1 passed")
            _emit(progress_callback, f"{candidate_id} guardrail 2 started")
            evaluation = evaluator_runner(workspace)
            _emit(progress_callback, f"{candidate_id} guardrail 2 passed")
            return Candidate(
                id=candidate_id,
                parent_id=parent.id,
                depth=parent.depth + 1,
                workspace=workspace,
                suggestion_trace=parent.suggestion_trace + (suggestion_title,),
                evaluation=evaluation,
                status="measured",
                retry_count=retries,
            )

        _emit(progress_callback, f"{candidate_id} guardrail 1 failed")
        _emit(progress_callback, feedback)
        retries += 1
        if retries > max_retries:
            return Candidate(
                id=candidate_id,
                parent_id=parent.id,
                depth=parent.depth + 1,
                workspace=workspace,
                suggestion_trace=parent.suggestion_trace + (suggestion_title,),
                status="failed",
                retry_count=retries - 1,
                selection_reason=str(feedback),
            )
