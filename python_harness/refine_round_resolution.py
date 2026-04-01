from collections.abc import Callable
from typing import Any

from python_harness.llm_client import load_llm_settings
from python_harness.refine_models import RefineRoundResult, SuggestionApplier


def resolve_suggestion_applier(
    applier: SuggestionApplier | None,
    *,
    llm_applier_factory: Callable[[], SuggestionApplier],
    null_applier_factory: Callable[[], SuggestionApplier],
) -> SuggestionApplier:
    if applier is not None:
        return applier
    settings = load_llm_settings()
    if settings.api_key:
        return llm_applier_factory()
    return null_applier_factory()


def resolve_self_check_runner(self_check_runner: Any | None) -> Any:
    if self_check_runner is not None:
        return self_check_runner
    from python_harness.refine_checks import default_self_check_runner

    return default_self_check_runner


def determine_stop_reason(
    *,
    round_result: RefineRoundResult,
    loop: bool,
    suggestions: list[dict[str, str]],
    winner_rank: tuple[Any, ...],
    baseline_rank: tuple[Any, ...],
) -> str:
    if round_result.stop_reason == "no suggestion applier configured":
        return round_result.stop_reason
    if not loop:
        return "single round completed"
    if not suggestions:
        return "winner has no suggestions"
    if winner_rank <= baseline_rank:
        return "winner did not improve baseline"
    return "max rounds reached"
