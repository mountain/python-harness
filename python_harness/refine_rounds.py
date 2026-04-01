from pathlib import Path
from typing import Any

from python_harness.hard_evaluator import HardEvaluator
from python_harness.qc_evaluator import QCEvaluator
from python_harness.refine_apply import (
    LLMSuggestionApplier,
    NullSuggestionApplier,
)
from python_harness.refine_models import RefineRoundResult, SuggestionApplier
from python_harness.refine_round_evaluation import (
    default_evaluator_runner as _default_evaluator_runner,
)
from python_harness.refine_round_evaluation import suggestions_from
from python_harness.refine_round_flow import run_refine_round as _run_refine_round
from python_harness.refine_round_loop import run_refine as _run_refine
from python_harness.refine_round_paths import (
    default_workspace_root,
    validate_workspace_root,
)
from python_harness.soft_evaluator import SoftEvaluator

__all__ = [
    "LLMSuggestionApplier",
    "NullSuggestionApplier",
    "HardEvaluator",
    "QCEvaluator",
    "SoftEvaluator",
    "default_evaluator_runner",
    "default_workspace_root",
    "validate_workspace_root",
    "suggestions_from",
    "run_refine_round",
    "run_refine",
]


def default_evaluator_runner(
    path: Path,
    progress_callback: Any = None,
    label: str = "baseline",
) -> dict[str, Any]:
    return _default_evaluator_runner(
        path,
        progress_callback=progress_callback,
        label=label,
        hard_evaluator_factory=HardEvaluator,
        qc_evaluator_factory=QCEvaluator,
        soft_evaluator_factory=SoftEvaluator,
    )


def run_refine_round(
    *,
    target_path: Path,
    workspace_root: Path,
    evaluator_runner: Any,
    applier: SuggestionApplier,
    self_check_runner: Any,
    max_retries: int,
    progress_callback: Any = None,
    baseline_evaluator_runner: Any | None = None,
) -> RefineRoundResult:
    resolved_baseline_runner = baseline_evaluator_runner
    if (
        resolved_baseline_runner is None
        and evaluator_runner is default_evaluator_runner
    ):
        def resolved_baseline_runner(path: Path) -> dict[str, Any]:
            return default_evaluator_runner(
                path,
                progress_callback=progress_callback,
                label="baseline",
            )

    return _run_refine_round(
        target_path=target_path,
        workspace_root=workspace_root,
        evaluator_runner=evaluator_runner,
        applier=applier,
        self_check_runner=self_check_runner,
        max_retries=max_retries,
        progress_callback=progress_callback,
        baseline_evaluator_runner=resolved_baseline_runner,
    )


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
    return _run_refine(
        target_path=target_path,
        workspace_root=workspace_root,
        max_retries=max_retries,
        loop=loop,
        max_rounds=max_rounds,
        evaluator_runner=evaluator_runner,
        applier=applier,
        self_check_runner=self_check_runner,
        progress_callback=progress_callback,
        default_evaluator_runner_fn=default_evaluator_runner,
        run_refine_round_fn=run_refine_round,
        default_workspace_root_fn=default_workspace_root,
        validate_workspace_root_fn=validate_workspace_root,
        llm_applier_factory=LLMSuggestionApplier,
        null_applier_factory=NullSuggestionApplier,
    )
