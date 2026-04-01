from dataclasses import dataclass
from pathlib import Path
from typing import Any

from python_harness.refine_feedback import (
    dominant_failure_signature,
    format_failure_feedback,
    parse_failure_feedback,
)
from python_harness.refine_models import Candidate


@dataclass(frozen=True, slots=True)
class GuardrailFailureResult:
    feedback_for_retry: str
    raw_feedback: str
    summary: str
    signature: str
    guardrail_entry: dict[str, Any]


def build_failed_candidate(
    *,
    parent: Candidate,
    candidate_id: str,
    workspace: Path,
    suggestion: dict[str, str],
    retry_count: int,
    reason: str,
    attempt_history: list[dict[str, Any]],
) -> Candidate:
    return Candidate(
        id=candidate_id,
        parent_id=parent.id,
        depth=parent.depth + 1,
        workspace=workspace,
        suggestion_trace=parent.suggestion_trace
        + (suggestion_title(suggestion, candidate_id),),
        suggestion=suggestion,
        status="failed",
        retry_count=retry_count,
        selection_reason=reason,
        attempt_history=attempt_history,
    )


def build_measured_candidate(
    *,
    parent: Candidate,
    candidate_id: str,
    workspace: Path,
    suggestion: dict[str, str],
    evaluation: dict[str, Any],
    retry_count: int,
    attempt_history: list[dict[str, Any]],
) -> Candidate:
    return Candidate(
        id=candidate_id,
        parent_id=parent.id,
        depth=parent.depth + 1,
        workspace=workspace,
        suggestion_trace=parent.suggestion_trace
        + (suggestion_title(suggestion, candidate_id),),
        suggestion=suggestion,
        evaluation=evaluation,
        status="measured",
        retry_count=retry_count,
        attempt_history=attempt_history,
    )


def suggestion_title(suggestion: dict[str, str], candidate_id: str) -> str:
    title = suggestion.get("title", "").strip()
    return title or candidate_id


def build_attempt_entry(
    *,
    attempt_number: int,
    suggestion_title: str,
    incoming_feedback: str,
) -> dict[str, Any]:
    return {
        "attempt": attempt_number,
        "suggestion_title": suggestion_title,
        "incoming_feedback": incoming_feedback,
    }


def build_guardrail_failure_result(
    *,
    pre_autofix_feedback: str,
    autofix_ok: bool,
    autofix_output: str,
    post_autofix_feedback: str,
) -> GuardrailFailureResult:
    pre_autofix_parsed = parse_failure_feedback(pre_autofix_feedback)
    post_autofix_parsed = parse_failure_feedback(post_autofix_feedback)
    formatted_feedback = format_failure_feedback(post_autofix_feedback)
    return GuardrailFailureResult(
        feedback_for_retry=formatted_feedback,
        raw_feedback=post_autofix_feedback,
        summary=str(post_autofix_parsed["summary"]),
        signature=dominant_failure_signature(post_autofix_feedback),
        guardrail_entry={
            "ok": False,
            "pre_autofix": {
                "raw": pre_autofix_feedback,
                "summary": pre_autofix_parsed["summary"],
                "failed_files": pre_autofix_parsed["failed_files"],
                "signatures": pre_autofix_parsed["signatures"],
            },
            "autofix": {"ok": autofix_ok, "output": autofix_output},
            "post_autofix": {
                "ok": False,
                "raw": post_autofix_feedback,
                "summary": post_autofix_parsed["summary"],
                "failed_files": post_autofix_parsed["failed_files"],
                "signatures": post_autofix_parsed["signatures"],
                "structured_feedback": formatted_feedback,
            },
        },
    )


def build_guardrail_autofix_success_entry(
    *,
    pre_autofix_feedback: str,
    autofix_ok: bool,
    autofix_output: str,
) -> dict[str, Any]:
    pre_autofix_parsed = parse_failure_feedback(pre_autofix_feedback)
    return {
        "ok": False,
        "pre_autofix": {
            "raw": pre_autofix_feedback,
            "summary": pre_autofix_parsed["summary"],
            "failed_files": pre_autofix_parsed["failed_files"],
            "signatures": pre_autofix_parsed["signatures"],
        },
        "autofix": {"ok": autofix_ok, "output": autofix_output},
        "post_autofix": {"ok": True},
    }


def advance_stagnation(
    previous_signature: str,
    previous_count: int,
    current_signature: str,
) -> tuple[str, int]:
    if current_signature == previous_signature:
        return current_signature, previous_count + 1
    return current_signature, 1
