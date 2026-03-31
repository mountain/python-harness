from pathlib import Path
from typing import Any

from python_harness.refine_models import Candidate, SuggestionApplier
from python_harness.refine_workspace import create_candidate_workspace


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
        except Exception as exc:
            feedback = str(exc)
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

        is_ok, feedback = self_check_runner(workspace)
        if is_ok:
            evaluation = evaluator_runner(workspace)
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
