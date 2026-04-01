from pathlib import Path
from typing import Any

from python_harness.hard_evaluator import HardEvaluator
from python_harness.llm_client import load_llm_settings
from python_harness.python_file_inventory import collect_python_files
from python_harness.qc_evaluator import QCEvaluator
from python_harness.refine_apply import (
    LLMSuggestionApplier,
    NullSuggestionApplier,
)
from python_harness.refine_execution import execute_candidate
from python_harness.refine_models import (
    Candidate,
    RefineRoundResult,
    SuggestionApplier,
)
from python_harness.refine_scoring import (
    build_candidate_rank,
    candidate_metrics,
    candidate_verdict,
    select_best_candidate,
)
from python_harness.refine_workspace import adopt_candidate_workspace
from python_harness.soft_evaluator import SoftEvaluator


def _emit(progress_callback: Any, message: str) -> None:
    if progress_callback is not None:
        progress_callback(message)


def _candidate_verdict(candidate: Candidate) -> str:
    return candidate_verdict(candidate)


def _candidate_total_tokens(candidate: Candidate) -> int:
    evaluation = candidate.evaluation or {}
    soft_evaluation = evaluation.get("soft_evaluation", {})
    if not isinstance(soft_evaluation, dict):
        return 0
    package_summary = soft_evaluation.get("package_summary", {})
    if not isinstance(package_summary, dict):
        return 0
    return int(package_summary.get("total_tokens", 0))


def _candidate_readability(candidate: Candidate) -> float:
    evaluation = candidate.evaluation or {}
    soft_evaluation = evaluation.get("soft_evaluation", {})
    if not isinstance(soft_evaluation, dict):
        return 0.0
    return float(soft_evaluation.get("understandability_score", 0.0))


def _candidate_loc(candidate: Candidate) -> int:
    total_lines = 0
    for file_path in collect_python_files(candidate.workspace):
        total_lines += len(file_path.read_text(encoding="utf-8").splitlines())
    return total_lines


def _scorecard_line(candidate: Candidate) -> str:
    metrics = candidate_metrics(candidate)
    hard = "fail" if metrics["hard_failed"] else "pass"
    qc = "fail" if metrics["qc_failed"] else "pass"
    return (
        f"{candidate.id} | status={candidate.status} | "
        f"loc={_candidate_loc(candidate)} | "
        f"tokens={_candidate_total_tokens(candidate)} | "
        f"readability={_candidate_readability(candidate):.1f} | "
        f"hard={hard} | qc={qc} | mi={metrics['avg_mi']:.1f} | "
        f"qa={metrics['qa_score']:.1f} | "
        f"cc={metrics['cc_issue_count']} | verdict={_candidate_verdict(candidate)}"
    )


def _winner_reason(winner: Candidate, baseline: Candidate) -> str:
    winner_rank = build_candidate_rank(winner)
    baseline_rank = build_candidate_rank(baseline)
    if winner.id == baseline.id:
        return f"{winner.id} remains best because no candidate beat baseline"
    return (
        f"{winner.id} beats baseline with rank {winner_rank} over {baseline_rank}"
    )


def default_evaluator_runner(
    path: Path,
    progress_callback: Any = None,
    label: str = "baseline",
) -> dict[str, Any]:
    _emit(progress_callback, f"{label} guardrail 1 started")
    hard_evaluator = HardEvaluator(str(path))
    hard_results = hard_evaluator.evaluate()
    if hard_results.get("all_passed", False):
        _emit(progress_callback, f"{label} guardrail 1 passed")
    else:
        _emit(progress_callback, f"{label} guardrail 1 failed")

    _emit(progress_callback, f"{label} guardrail 2 started")
    qc_evaluator = QCEvaluator(str(path))
    qc_results = qc_evaluator.evaluate()
    if qc_results.get("all_passed", False):
        _emit(progress_callback, f"{label} guardrail 2 passed")
    else:
        _emit(progress_callback, f"{label} guardrail 2 failed")

    _emit(progress_callback, f"{label} soft evaluation started")
    soft_evaluator = SoftEvaluator(str(path))
    soft_results = soft_evaluator.evaluate()
    final_report = soft_evaluator.generate_final_report(
        hard_results,
        qc_results,
        soft_results,
    )
    _emit(progress_callback, f"{label} soft evaluation passed")
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
    progress_callback: Any = None,
) -> RefineRoundResult:
    def evaluate_baseline(path: Path) -> dict[str, Any]:
        if evaluator_runner is default_evaluator_runner:
            return default_evaluator_runner(
                path,
                progress_callback=progress_callback,
                label="baseline",
            )
        return dict(evaluator_runner(path))

    def evaluate_candidate(path: Path, label: str) -> dict[str, Any]:
        _emit(progress_callback, f"{label} guardrail 2 measure started")
        result = dict(evaluator_runner(path))
        _emit(progress_callback, f"{label} guardrail 2 completed")
        return result

    _emit(progress_callback, "baseline measure started")
    baseline = Candidate(
        id="baseline",
        parent_id=None,
        depth=0,
        workspace=target_path,
        suggestion_trace=(),
        evaluation=evaluate_baseline(target_path),
        status="measured",
    )
    _emit(progress_callback, "baseline measure passed")
    round_result = RefineRoundResult(baseline=baseline)
    if (
        isinstance(applier, NullSuggestionApplier)
        and suggestions_from(baseline.evaluation)
    ):
        round_result.winner = baseline
        round_result.stop_reason = "no suggestion applier configured"
        return round_result

    first_layer: list[Candidate] = []
    completed_candidates = 0
    discovered_candidates = len(suggestions_from(baseline.evaluation))

    for index, suggestion in enumerate(suggestions_from(baseline.evaluation), start=1):
        candidate_id = f"l1-{index}"
        _emit(
            progress_callback,
            f"candidate {completed_candidates + 1}/{discovered_candidates} started: "
            f"{candidate_id}",
        )
        candidate = execute_candidate(
            parent=baseline,
            candidate_id=candidate_id,
            suggestion=suggestion,
            workspace_root=workspace_root,
            applier=applier,
            self_check_runner=self_check_runner,
            evaluator_runner=lambda path, label=f"l1-{index}": evaluate_candidate(
                path,
                label,
            ),
            max_retries=max_retries,
            progress_callback=progress_callback,
        )
        completed_candidates += 1
        _emit(
            progress_callback,
            f"candidate {completed_candidates}/{discovered_candidates} completed: "
            f"{candidate.id} ({candidate.status})",
        )
        round_result.candidates.append(candidate)
        first_layer.append(candidate)
        if candidate.status == "measured" and candidate.evaluation:
            discovered_candidates += len(suggestions_from(candidate.evaluation))

    for parent in first_layer:
        if parent.status != "measured" or not parent.evaluation:
            continue
        for index, suggestion in enumerate(
            suggestions_from(parent.evaluation),
            start=1,
        ):
            candidate_id = f"{parent.id}-l2-{index}"
            _emit(
                progress_callback,
                (
                    "candidate "
                    f"{completed_candidates + 1}/{discovered_candidates} "
                    f"started: {candidate_id}"
                ),
            )
            candidate = execute_candidate(
                parent=parent,
                candidate_id=candidate_id,
                suggestion=suggestion,
                workspace_root=workspace_root,
                applier=applier,
                self_check_runner=self_check_runner,
                evaluator_runner=lambda path, label=f"{parent.id}-l2-{index}": (
                    evaluate_candidate(path, label)
                ),
                max_retries=max_retries,
                progress_callback=progress_callback,
            )
            completed_candidates += 1
            _emit(
                progress_callback,
                f"candidate {completed_candidates}/{discovered_candidates} completed: "
                f"{candidate.id} ({candidate.status})",
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
    progress_callback: Any = None,
) -> dict[str, Any]:
    target_path = target_path.resolve()
    evaluator = evaluator_runner or default_evaluator_runner
    suggestion_applier = applier
    if suggestion_applier is None:
        settings = load_llm_settings()
        suggestion_applier = (
            LLMSuggestionApplier() if settings.api_key else NullSuggestionApplier()
        )
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
        _emit(progress_callback, f"round {rounds_completed + 1} started")
        round_result = run_refine_round(
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
        _emit(
            progress_callback,
            f"round {rounds_completed} selection winner: "
            f"{winner_id} ({round_result.stop_reason})",
        )
        _emit(progress_callback, f"round {rounds_completed} scorecard:")
        for candidate in [round_result.baseline, *round_result.candidates]:
            _emit(progress_callback, _scorecard_line(candidate))
        _emit(
            progress_callback,
            f"round {rounds_completed} winner reason: "
            f"{_winner_reason(winner, round_result.baseline)}",
        )

        baseline_rank = build_candidate_rank(round_result.baseline)
        winner_rank = build_candidate_rank(winner)
        suggestions = suggestions_from(winner.evaluation)

        if round_result.stop_reason == "no suggestion applier configured":
            stop_reason = round_result.stop_reason
            _emit(progress_callback, f"round {rounds_completed} stopped: {stop_reason}")
            break

        if winner.workspace != target_path:
            adopt_candidate_workspace(winner.workspace, target_path)
            _emit(
                progress_callback,
                f"round {rounds_completed} adopted winner workspace: {winner.id}",
            )

        if not loop:
            stop_reason = "single round completed"
            _emit(progress_callback, f"round {rounds_completed} stopped: {stop_reason}")
            break
        if not suggestions:
            stop_reason = "winner has no suggestions"
            _emit(progress_callback, f"round {rounds_completed} stopped: {stop_reason}")
            break
        if winner_rank <= baseline_rank:
            stop_reason = "winner did not improve baseline"
            _emit(progress_callback, f"round {rounds_completed} stopped: {stop_reason}")
            break

    return {
        "rounds_completed": rounds_completed,
        "winner_id": winner_id,
        "stop_reason": stop_reason,
    }
