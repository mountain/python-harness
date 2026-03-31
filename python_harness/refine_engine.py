import subprocess
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

from python_harness.evaluator import Evaluator
from python_harness.refine_apply import NullSuggestionApplier
from python_harness.refine_models import (
    Candidate,
    RefineRoundResult,
    SuggestionApplier,
)
from python_harness.refine_scoring import (
    build_candidate_rank,
    select_best_candidate,
)
from python_harness.refine_workspace import (
    adopt_candidate_workspace,
    create_candidate_workspace,
)

SelfCheckRunner = Callable[[Path], tuple[bool, str]]
EvaluatorRunner = Callable[[Path], dict[str, Any]]


def _default_evaluator_runner(path: Path) -> dict[str, Any]:
    return Evaluator(str(path)).run()


def _run_command(path: Path, args: list[str]) -> tuple[bool, str]:
    command_cwd = path if path.is_dir() else path.parent
    completed = subprocess.run(
        args,
        cwd=command_cwd,
        capture_output=True,
        text=True,
        check=False,
    )
    output = (completed.stdout + completed.stderr).strip()
    return completed.returncode == 0, output


def _default_self_check_runner(path: Path) -> tuple[bool, str]:
    checks = [
        [sys.executable, "-m", "ruff", "check", str(path)],
        [sys.executable, "-m", "mypy", str(path)],
        [sys.executable, "-m", "pytest", str(path)],
    ]
    for args in checks:
        ok, output = _run_command(path, args)
        if not ok:
            return False, output
    return True, ""


def _suggestions_from(evaluation: dict[str, Any] | None) -> list[dict[str, str]]:
    if not evaluation:
        return []
    final_report = evaluation.get("final_report", {})
    raw_suggestions = final_report.get("suggestions", [])
    return [
        suggestion
        for suggestion in raw_suggestions
        if isinstance(suggestion, dict) and "title" in suggestion
    ][:3]


def _default_workspace_root(target_path: Path) -> Path:
    return target_path.parent / f".harness-refine-{target_path.name}"


def _validate_workspace_root(target_path: Path, workspace_root: Path) -> None:
    if workspace_root == target_path or workspace_root.is_relative_to(target_path):
        raise ValueError("workspace_root must not be inside target_path")


def execute_candidate(
    *,
    parent: Candidate,
    candidate_id: str,
    suggestion: dict[str, str],
    workspace_root: Path,
    applier: SuggestionApplier,
    self_check_runner: SelfCheckRunner,
    evaluator_runner: EvaluatorRunner,
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
        apply_result: dict[str, Any] | None = None
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


def run_refine_round(
    *,
    target_path: Path,
    workspace_root: Path,
    evaluator_runner: EvaluatorRunner,
    applier: SuggestionApplier,
    self_check_runner: SelfCheckRunner,
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

    first_layer: list[Candidate] = []
    for index, suggestion in enumerate(_suggestions_from(baseline.evaluation), start=1):
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
            _suggestions_from(parent.evaluation), start=1
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
    evaluator_runner: EvaluatorRunner | None = None,
    applier: SuggestionApplier | None = None,
    self_check_runner: SelfCheckRunner | None = None,
) -> dict[str, Any]:
    target_path = target_path.resolve()
    evaluator = evaluator_runner or _default_evaluator_runner
    suggestion_applier = applier or NullSuggestionApplier()
    self_check = self_check_runner or _default_self_check_runner
    resolved_workspace_root = (
        workspace_root.resolve()
        if workspace_root is not None
        else _default_workspace_root(target_path)
    )
    _validate_workspace_root(target_path, resolved_workspace_root)
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
        suggestions = _suggestions_from(winner.evaluation)

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
