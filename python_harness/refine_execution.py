from pathlib import Path
from typing import Any

from python_harness.refine_checks import default_autofix_runner
from python_harness.refine_execution_support import (
    advance_stagnation,
    build_attempt_entry,
    build_failed_candidate,
    build_guardrail_autofix_success_entry,
    build_guardrail_failure_result,
    build_measured_candidate,
    suggestion_title,
)
from python_harness.refine_models import Candidate, SuggestionApplier
from python_harness.refine_workspace import create_candidate_workspace

_STAGNATION_LIMIT = 3


def _emit(progress_callback: Any, message: str) -> None:
    if progress_callback is not None:
        progress_callback(message)


def _apply_suggestion(
    *,
    workspace: Path,
    suggestion: dict[str, str],
    feedback: str,
    applier: SuggestionApplier,
) -> tuple[bool, str, bool, dict[str, Any]]:
    apply_result: dict[str, Any] | None = None
    try:
        apply_result = applier.apply(
            workspace,
            suggestion,
            failure_feedback=feedback,
        )
        if not bool(apply_result.get("ok", False)):
            failure_reason = str(
                apply_result.get("failure_reason") or "suggestion apply failed"
            )
            retryable = bool(apply_result.get("retryable", True))
            return (
                False,
                failure_reason,
                retryable,
                {
                    "ok": False,
                    "failure_reason": failure_reason,
                    "retryable": retryable,
                },
            )
        return (
            True,
            "",
            True,
            {
                "ok": True,
                "touched_files": list(apply_result.get("touched_files", [])),
            },
        )
    except Exception as exc:
        failure_reason = str(exc)
        retryable = True
        if apply_result is not None:
            retryable = bool(apply_result.get("retryable", True))
        return (
            False,
            failure_reason,
            retryable,
            {
                "ok": False,
                "failure_reason": failure_reason,
                "retryable": retryable,
            },
        )


def _run_guardrail_cycle(
    *,
    workspace: Path,
    candidate_id: str,
    self_check_runner: Any,
    autofix_runner: Any,
    progress_callback: Any,
) -> tuple[bool, str, str, str, str, dict[str, Any]]:
    _emit(progress_callback, f"{candidate_id} guardrail 1 started")
    is_ok, feedback = self_check_runner(workspace)
    if is_ok:
        _emit(progress_callback, f"{candidate_id} guardrail 1 passed")
        return True, "", "", "", "", {"ok": True}

    _emit(progress_callback, f"{candidate_id} guardrail 1 failed")
    _emit(progress_callback, feedback)
    _emit(progress_callback, f"{candidate_id} guardrail 1 autofix started")
    autofix_ok, autofix_output = autofix_runner(workspace)
    if autofix_ok:
        _emit(progress_callback, f"{candidate_id} guardrail 1 autofix passed")
    else:
        _emit(progress_callback, f"{candidate_id} guardrail 1 autofix failed")
        if autofix_output:
            _emit(progress_callback, autofix_output)

    post_autofix_ok, post_autofix_feedback = self_check_runner(workspace)
    if post_autofix_ok:
        _emit(progress_callback, f"{candidate_id} guardrail 1 passed")
        return (
            True,
            "",
            "",
            "",
            "",
            build_guardrail_autofix_success_entry(
                pre_autofix_feedback=feedback,
                autofix_ok=autofix_ok,
                autofix_output=autofix_output,
            ),
        )

    failure_result = build_guardrail_failure_result(
        pre_autofix_feedback=feedback,
        autofix_ok=autofix_ok,
        autofix_output=autofix_output,
        post_autofix_feedback=post_autofix_feedback,
    )
    return (
        False,
        failure_result.feedback_for_retry,
        failure_result.raw_feedback,
        failure_result.summary,
        failure_result.signature,
        failure_result.guardrail_entry,
    )


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
    autofix_runner: Any = default_autofix_runner,
    progress_callback: Any = None,
) -> Candidate:
    workspace = create_candidate_workspace(
        parent.workspace,
        workspace_root,
        candidate_id,
    )
    feedback = ""
    retries = 0
    current_suggestion_title = suggestion_title(suggestion, candidate_id)
    attempt_history: list[dict[str, Any]] = []
    last_guardrail_signature = ""
    stagnation_count = 0

    while True:
        attempt_number = retries + 1
        attempt_entry = build_attempt_entry(
            attempt_number=attempt_number,
            suggestion_title=current_suggestion_title,
            incoming_feedback=feedback,
        )
        _emit(
            progress_callback,
            f"{candidate_id} apply started: {current_suggestion_title}",
        )
        apply_ok, feedback, retryable, apply_entry = _apply_suggestion(
            workspace=workspace,
            suggestion=suggestion,
            feedback=feedback,
            applier=applier,
        )
        attempt_entry["apply"] = apply_entry
        if not apply_ok:
            attempt_history.append(attempt_entry)
            _emit(progress_callback, f"{candidate_id} apply failed: {feedback}")
            if not retryable:
                return build_failed_candidate(
                    parent=parent,
                    candidate_id=candidate_id,
                    workspace=workspace,
                    suggestion=suggestion,
                    retry_count=retries,
                    reason=feedback,
                    attempt_history=attempt_history,
                )
            retries += 1
            if retries > max_retries:
                return build_failed_candidate(
                    parent=parent,
                    candidate_id=candidate_id,
                    workspace=workspace,
                    suggestion=suggestion,
                    retry_count=retries - 1,
                    reason=feedback,
                    attempt_history=attempt_history,
                )
            continue
        _emit(progress_callback, f"{candidate_id} apply passed")

        (
            guardrail_passed,
            feedback,
            guardrail_failure_reason,
            guardrail_summary,
            current_signature,
            guardrail_entry,
        ) = (
            _run_guardrail_cycle(
                workspace=workspace,
                candidate_id=candidate_id,
                self_check_runner=self_check_runner,
                autofix_runner=autofix_runner,
                progress_callback=progress_callback,
            )
        )
        attempt_entry["guardrail"] = guardrail_entry
        attempt_history.append(attempt_entry)
        if guardrail_passed:
            _emit(progress_callback, f"{candidate_id} guardrail 2 started")
            evaluation = evaluator_runner(workspace)
            _emit(progress_callback, f"{candidate_id} guardrail 2 passed")
            return build_measured_candidate(
                parent=parent,
                candidate_id=candidate_id,
                workspace=workspace,
                suggestion=suggestion,
                evaluation=evaluation,
                retry_count=retries,
                attempt_history=attempt_history,
            )

        last_guardrail_signature, stagnation_count = advance_stagnation(
            last_guardrail_signature,
            stagnation_count,
            current_signature,
        )
        if stagnation_count >= _STAGNATION_LIMIT:
            return build_failed_candidate(
                parent=parent,
                candidate_id=candidate_id,
                workspace=workspace,
                suggestion=suggestion,
                retry_count=retries,
                reason=f"stalled on repeated guardrail failures: {guardrail_summary}",
                attempt_history=attempt_history,
            )
        retries += 1
        if retries > max_retries:
            return build_failed_candidate(
                parent=parent,
                candidate_id=candidate_id,
                workspace=workspace,
                suggestion=suggestion,
                retry_count=retries - 1,
                reason=guardrail_failure_reason,
                attempt_history=attempt_history,
            )
