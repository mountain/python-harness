from collections.abc import Callable
from pathlib import Path
from typing import Any

from python_harness.refine_checks import default_self_check_runner
from python_harness.refine_execution import (
    execute_candidate as _execute_candidate,
)
from python_harness.refine_rounds import (
    default_evaluator_runner,
    default_workspace_root,
    suggestions_from,
    validate_workspace_root,
)
from python_harness.refine_rounds import (
    run_refine as _run_refine,
)
from python_harness.refine_rounds import (
    run_refine_round as _run_refine_round,
)

SelfCheckRunner = Callable[[Path], tuple[bool, str]]
EvaluatorRunner = Callable[[Path], dict[str, Any]]

_default_evaluator_runner = default_evaluator_runner
_default_self_check_runner = default_self_check_runner
_default_workspace_root = default_workspace_root
_suggestions_from = suggestions_from
_validate_workspace_root = validate_workspace_root


def execute_candidate(*args: Any, **kwargs: Any) -> Any:
    return _execute_candidate(*args, **kwargs)


def run_refine_round(*args: Any, **kwargs: Any) -> Any:
    return _run_refine_round(*args, **kwargs)


def run_refine(*args: Any, **kwargs: Any) -> Any:
    return _run_refine(*args, **kwargs)
