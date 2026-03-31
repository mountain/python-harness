from typing import Any

from python_harness.refine_models import Candidate, SelectionResult
from python_harness.soft_eval_report import extract_metrics


def _normalized_status(candidate: Candidate) -> str:
    if candidate.status == "pending" and candidate.evaluation is not None:
        return "measured"
    return candidate.status


def candidate_metrics(candidate: Candidate) -> dict[str, Any]:
    if candidate.evaluation is None:
        return {
            "avg_mi": 0.0,
            "qa_score": 0.0,
            "cc_issue_count": 0,
            "hard_failed": True,
            "qc_failed": True,
        }

    evaluation = candidate.evaluation or {}
    raw_metrics = evaluation.get("metrics")
    if isinstance(raw_metrics, dict):
        cc_issue_count = raw_metrics.get("cc_issue_count")
        if cc_issue_count is None:
            cc_issue_count = len(raw_metrics.get("cc_issues", []))
        return {
            "avg_mi": float(raw_metrics.get("avg_mi", 0.0)),
            "qa_score": float(raw_metrics.get("qa_score", 0.0)),
            "cc_issue_count": int(cc_issue_count),
            "hard_failed": bool(raw_metrics.get("hard_failed", True)),
            "qc_failed": bool(raw_metrics.get("qc_failed", True)),
        }

    hard = evaluation.get("hard_evaluation", {})
    qc = evaluation.get("qc_evaluation", {})
    soft = evaluation.get("soft_evaluation", {})
    derived = extract_metrics(hard, qc, soft)
    return {
        "avg_mi": float(derived["avg_mi"]),
        "qa_score": float(derived["qa_score"]),
        "cc_issue_count": len(derived["cc_issues"]),
        "hard_failed": bool(derived["hard_failed"]),
        "qc_failed": bool(derived["qc_failed"]),
    }


def build_candidate_rank(
    candidate: Candidate,
) -> tuple[int, int, int, float, float, int]:
    status_priority = {
        "measured": 2,
        "pending": 1,
        "failed": 0,
    }
    metrics = candidate_metrics(candidate)
    verdict = str(
        (candidate.evaluation or {}).get("final_report", {}).get("verdict", "Fail")
    ).strip()
    normalized_status = _normalized_status(candidate)
    passes_hard_qc = int(not metrics["hard_failed"] and not metrics["qc_failed"])
    verdict_is_pass = int(verdict.startswith("Pass"))
    return (
        status_priority.get(normalized_status, 0),
        passes_hard_qc,
        verdict_is_pass,
        float(metrics["avg_mi"]),
        float(metrics["qa_score"]),
        -int(metrics["cc_issue_count"]),
    )


def select_best_candidate(candidates: list[Candidate]) -> SelectionResult:
    if not candidates:
        raise ValueError("select_best_candidate requires at least one candidate")

    ordered = sorted(candidates, key=build_candidate_rank, reverse=True)
    winner = ordered[0]
    winner_rank = build_candidate_rank(winner)
    return SelectionResult(
        winner=winner,
        ordered_ids=[candidate.id for candidate in ordered],
        reason=f"selected by rank {winner_rank}",
    )
