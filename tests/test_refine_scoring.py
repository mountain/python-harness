from pathlib import Path

from python_harness.refine_models import Candidate
from python_harness.refine_scoring import (
    build_candidate_rank,
    candidate_verdict,
    select_best_candidate,
)


def make_candidate(
    candidate_id: str,
    *,
    verdict: str,
    hard_passed: bool,
    qc_passed: bool,
    avg_mi: float,
    qa_score: float,
    cc_issues: int,
) -> Candidate:
    return Candidate(
        id=candidate_id,
        parent_id=None,
        depth=0,
        workspace=Path("/tmp") / candidate_id,
        suggestion_trace=(),
        evaluation={
            "hard_evaluation": {"all_passed": hard_passed},
            "qc_evaluation": {"all_passed": qc_passed, "failures": []},
            "soft_evaluation": {"understandability_score": qa_score},
            "final_report": {"verdict": verdict},
            "metrics": {
                "avg_mi": avg_mi,
                "qa_score": qa_score,
                "cc_issue_count": cc_issues,
                "hard_failed": not hard_passed,
                "qc_failed": not qc_passed,
            },
        },
    )


def test_build_candidate_rank_prioritizes_passing_hard_and_qc() -> None:
    failed = make_candidate(
        "failed",
        verdict="Fail",
        hard_passed=False,
        qc_passed=True,
        avg_mi=95.0,
        qa_score=95.0,
        cc_issues=0,
    )
    passed = make_candidate(
        "passed",
        verdict="Fail",
        hard_passed=True,
        qc_passed=True,
        avg_mi=60.0,
        qa_score=60.0,
        cc_issues=1,
    )
    assert build_candidate_rank(passed) > build_candidate_rank(failed)


def test_select_best_candidate_compares_all_metrics_deterministically() -> None:
    low = make_candidate(
        "low",
        verdict="Pass",
        hard_passed=True,
        qc_passed=True,
        avg_mi=71.0,
        qa_score=76.0,
        cc_issues=1,
    )
    high = make_candidate(
        "high",
        verdict="Pass",
        hard_passed=True,
        qc_passed=True,
        avg_mi=85.0,
        qa_score=90.0,
        cc_issues=0,
    )
    result = select_best_candidate([low, high])
    assert result.winner.id == "high"
    assert result.ordered_ids == ["high", "low"]


def test_select_best_candidate_penalizes_unmeasured_candidates() -> None:
    pending = Candidate(
        id="pending",
        parent_id=None,
        depth=0,
        workspace=Path("/tmp/pending"),
        suggestion_trace=(),
        status="pending",
        evaluation=None,
    )
    measured = make_candidate(
        "measured",
        verdict="Fail",
        hard_passed=True,
        qc_passed=True,
        avg_mi=10.0,
        qa_score=10.0,
        cc_issues=10,
    )

    result = select_best_candidate([pending, measured])

    assert result.winner.id == "measured"
    assert result.ordered_ids == ["measured", "pending"]


def test_select_best_candidate_penalizes_failed_candidates_even_with_high_scores(
) -> None:
    failed = make_candidate(
        "failed",
        verdict="Pass",
        hard_passed=True,
        qc_passed=True,
        avg_mi=99.0,
        qa_score=99.0,
        cc_issues=0,
    )
    failed.status = "failed"
    measured = make_candidate(
        "measured",
        verdict="Fail",
        hard_passed=True,
        qc_passed=True,
        avg_mi=20.0,
        qa_score=20.0,
        cc_issues=3,
    )

    result = select_best_candidate([failed, measured])

    assert result.winner.id == "measured"
    assert result.ordered_ids == ["measured", "failed"]


def test_build_candidate_rank_treats_pass_mock_as_pass() -> None:
    mock_pass = make_candidate(
        "mock-pass",
        verdict="Pass (Mock)",
        hard_passed=True,
        qc_passed=True,
        avg_mi=70.0,
        qa_score=80.0,
        cc_issues=0,
    )
    fail = make_candidate(
        "fail",
        verdict="Fail",
        hard_passed=True,
        qc_passed=True,
        avg_mi=70.0,
        qa_score=80.0,
        cc_issues=0,
    )

    assert build_candidate_rank(mock_pass) > build_candidate_rank(fail)


def test_candidate_verdict_forces_fail_when_hard_or_qc_failed() -> None:
    inconsistent = make_candidate(
        "inconsistent",
        verdict="Pass",
        hard_passed=False,
        qc_passed=True,
        avg_mi=95.0,
        qa_score=99.0,
        cc_issues=0,
    )

    assert candidate_verdict(inconsistent) == "Fail"
