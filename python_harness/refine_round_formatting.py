from python_harness.python_file_inventory import collect_python_files
from python_harness.refine_models import Candidate, RefineRoundResult
from python_harness.refine_scoring import (
    build_candidate_rank,
    candidate_metrics,
    candidate_verdict,
)


def candidate_total_tokens(candidate: Candidate) -> int:
    evaluation = candidate.evaluation or {}
    soft_evaluation = evaluation.get("soft_evaluation", {})
    if not isinstance(soft_evaluation, dict):
        return 0
    package_summary = soft_evaluation.get("package_summary", {})
    if not isinstance(package_summary, dict):
        return 0
    return int(package_summary.get("total_tokens", 0))


def candidate_readability(candidate: Candidate) -> float:
    evaluation = candidate.evaluation or {}
    soft_evaluation = evaluation.get("soft_evaluation", {})
    if not isinstance(soft_evaluation, dict):
        return 0.0
    return float(soft_evaluation.get("understandability_score", 0.0))


def candidate_loc(candidate: Candidate) -> int:
    total_lines = 0
    for file_path in collect_python_files(candidate.workspace):
        total_lines += len(file_path.read_text(encoding="utf-8").splitlines())
    return total_lines


def scorecard_line(candidate: Candidate) -> str:
    metrics = candidate_metrics(candidate)
    hard = "fail" if metrics["hard_failed"] else "pass"
    qc = "fail" if metrics["qc_failed"] else "pass"
    return (
        f"{candidate.id} | status={candidate.status} | "
        f"loc={candidate_loc(candidate)} | "
        f"tokens={candidate_total_tokens(candidate)} | "
        f"readability={candidate_readability(candidate):.1f} | "
        f"hard={hard} | qc={qc} | mi={metrics['avg_mi']:.1f} | "
        f"qa={metrics['qa_score']:.1f} | "
        f"cc={metrics['cc_issue_count']} | verdict={candidate_verdict(candidate)}"
    )


def winner_reason(winner: Candidate, baseline: Candidate) -> str:
    winner_rank = build_candidate_rank(winner)
    baseline_rank = build_candidate_rank(baseline)
    if winner.id == baseline.id:
        return f"{winner.id} remains best because no candidate beat baseline"
    return (
        f"{winner.id} beats baseline with rank {winner_rank} over {baseline_rank}"
    )


def round_candidates(round_result: RefineRoundResult) -> list[Candidate]:
    return [round_result.baseline, *round_result.candidates]


def round_scorecards(round_result: RefineRoundResult) -> dict[str, str]:
    return {
        candidate.id: scorecard_line(candidate)
        for candidate in round_candidates(round_result)
    }
