from pathlib import Path

from python_harness.refine_apply import NullSuggestionApplier
from python_harness.refine_round_evaluation import suggestions_from
from python_harness.refine_round_flow import run_refine_round
from python_harness.refine_round_loop import run_refine


def test_refine_round_evaluation_suggestions_from_filters_to_files() -> None:
    suggestions = suggestions_from(
        {
            "final_report": {
                "suggestions": [
                    {"title": "Missing target", "description": "d1"},
                    {
                        "title": "All files",
                        "description": "d2",
                        "target_file": "all",
                    },
                    {
                        "title": "Dir target",
                        "description": "d3",
                        "target_file": "tests/",
                    },
                    {
                        "title": "Specific file",
                        "description": "d4",
                        "target_file": "python_harness/refine_scoring.py",
                    },
                ]
            }
        }
    )

    assert suggestions == [
        {
            "title": "Specific file",
            "description": "d4",
            "target_file": "python_harness/refine_scoring.py",
        }
    ]


def test_refine_round_flow_stops_early_without_real_suggestion_applier(
    tmp_path: Path,
) -> None:
    target = tmp_path / "baseline"
    target.mkdir()
    (target / "sample.py").write_text("print('baseline')\n")
    calls = {"count": 0}

    def evaluator(_: Path) -> dict[str, object]:
        calls["count"] += 1
        return {
            "hard_evaluation": {"all_passed": True},
            "qc_evaluation": {"all_passed": True, "failures": []},
            "soft_evaluation": {"understandability_score": 80.0},
            "final_report": {
                "verdict": "Fail",
                "suggestions": [
                    {"title": "S1", "description": "d1", "target_file": "sample.py"},
                    {"title": "S2", "description": "d2", "target_file": "sample.py"},
                    {"title": "S3", "description": "d3", "target_file": "sample.py"},
                ],
            },
        }

    result = run_refine_round(
        target_path=target,
        workspace_root=tmp_path / "runs",
        evaluator_runner=evaluator,
        applier=NullSuggestionApplier(),
        self_check_runner=lambda _: (True, ""),
        max_retries=0,
    )

    assert calls["count"] == 1
    assert result.winner is not None
    assert result.winner.id == "baseline"
    assert result.candidates == []
    assert result.stop_reason == "no suggestion applier configured"


def test_refine_round_loop_stops_when_winner_has_no_suggestions(
    tmp_path: Path,
) -> None:
    target = tmp_path / "target"
    target.mkdir()
    (target / "sample.py").write_text("print('baseline')\n")

    def evaluator(_: Path) -> dict[str, object]:
        return {
            "hard_evaluation": {"all_passed": True},
            "qc_evaluation": {"all_passed": True, "failures": []},
            "soft_evaluation": {"understandability_score": 80.0},
            "final_report": {"verdict": "Fail", "suggestions": []},
            "metrics": {
                "avg_mi": 70.0,
                "qa_score": 80.0,
                "cc_issue_count": 0,
                "hard_failed": False,
                "qc_failed": False,
            },
        }

    result = run_refine(
        target_path=target,
        max_retries=0,
        loop=True,
        max_rounds=3,
        evaluator_runner=evaluator,
    )

    assert result["rounds_completed"] == 1
    assert result["winner_id"] == "baseline"
    assert result["stop_reason"] == "winner has no suggestions"
