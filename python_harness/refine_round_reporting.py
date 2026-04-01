from pathlib import Path
from typing import Any

from python_harness.refine_artifacts import persist_round_artifact
from python_harness.refine_models import Candidate, RefineRoundResult
from python_harness.refine_round_formatting import round_candidates


def emit_round_summary(
    round_number: int,
    round_result: RefineRoundResult,
    winner: Candidate,
    scorecards: dict[str, str],
    winner_summary: str,
    progress_callback: Any,
) -> None:
    if progress_callback is None:
        return
    progress_callback(
        f"round {round_number} selection winner: "
        f"{winner.id} ({round_result.stop_reason})"
    )
    progress_callback(f"round {round_number} scorecard:")
    for candidate in round_candidates(round_result):
        progress_callback(scorecards[candidate.id])
    progress_callback(f"round {round_number} winner reason: {winner_summary}")


def emit_stop_reason(
    round_number: int,
    stop_reason: str,
    progress_callback: Any,
) -> None:
    if progress_callback is None or stop_reason == "max rounds reached":
        return
    progress_callback(f"round {round_number} stopped: {stop_reason}")


def persist_round(
    *,
    workspace_root: Path,
    round_number: int,
    round_result: RefineRoundResult,
    stop_reason: str,
    winner_summary: str,
    scorecards: dict[str, str],
) -> None:
    persist_round_artifact(
        workspace_root=workspace_root,
        round_number=round_number,
        round_result=round_result,
        stop_reason=stop_reason,
        winner_reason=winner_summary,
        scorecards=scorecards,
    )
