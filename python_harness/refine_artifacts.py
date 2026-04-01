import json
from pathlib import Path
from typing import Any

from python_harness.refine_models import Candidate, RefineRoundResult


def _evaluation_summary(evaluation: dict[str, Any] | None) -> dict[str, Any]:
    if not evaluation:
        return {}
    final_report = evaluation.get("final_report", {})
    metrics = evaluation.get("metrics", {})
    return {
        "verdict": final_report.get("verdict", ""),
        "summary": final_report.get("summary", ""),
        "suggestion_count": len(final_report.get("suggestions", [])),
        "metrics": metrics if isinstance(metrics, dict) else {},
    }


def _candidate_payload(candidate: Candidate, scorecard: str) -> dict[str, Any]:
    return {
        "id": candidate.id,
        "parent_id": candidate.parent_id,
        "depth": candidate.depth,
        "status": candidate.status,
        "workspace": str(candidate.workspace),
        "retry_count": candidate.retry_count,
        "selection_reason": candidate.selection_reason,
        "suggestion_trace": list(candidate.suggestion_trace),
        "suggestion": candidate.suggestion or {},
        "attempts": candidate.attempt_history,
        "scorecard": scorecard,
        "evaluation": _evaluation_summary(candidate.evaluation),
    }


def persist_round_artifact(
    *,
    workspace_root: Path,
    round_number: int,
    round_result: RefineRoundResult,
    stop_reason: str,
    winner_reason: str,
    scorecards: dict[str, str],
) -> Path:
    artifact_dir = workspace_root / "artifacts"
    artifact_dir.mkdir(parents=True, exist_ok=True)
    winner = round_result.winner or round_result.baseline
    payload = {
        "round": round_number,
        "winner_id": winner.id,
        "selection_reason": round_result.stop_reason,
        "stop_reason": stop_reason,
        "winner_reason": winner_reason,
        "baseline": _candidate_payload(
            round_result.baseline,
            scorecards[round_result.baseline.id],
        ),
        "candidates": [
            _candidate_payload(candidate, scorecards[candidate.id])
            for candidate in round_result.candidates
        ],
    }
    artifact_path = artifact_dir / f"round-{round_number:03d}.json"
    artifact_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return artifact_path
