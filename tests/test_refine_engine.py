import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from python_harness import refine_checks
from python_harness.refine_apply import NullSuggestionApplier
from python_harness.refine_engine import execute_candidate, run_refine, run_refine_round
from python_harness.refine_models import Candidate
from python_harness.refine_rounds import suggestions_from


class FlakyApplier:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def apply(
        self,
        workspace: Path,
        suggestion: dict[str, str],
        failure_feedback: str = "",
    ) -> dict[str, object]:
        self.calls.append(failure_feedback)
        return {
            "ok": True,
            "touched_files": [workspace.name, suggestion["title"]],
            "failure_reason": "",
        }


class StaticSuccessApplier:
    def apply(
        self,
        workspace: Path,
        suggestion: dict[str, str],
        failure_feedback: str = "",
    ) -> dict[str, object]:
        del workspace, suggestion, failure_feedback
        return {"ok": True, "touched_files": [], "failure_reason": ""}


class NonRetryableFailureApplier:
    def __init__(self) -> None:
        self.calls = 0

    def apply(
        self,
        workspace: Path,
        suggestion: dict[str, str],
        failure_feedback: str = "",
    ) -> dict[str, object]:
        del workspace, suggestion, failure_feedback
        self.calls += 1
        return {
            "ok": False,
            "touched_files": [],
            "failure_reason": "Request timed out.",
            "retryable": False,
        }


def test_execute_candidate_passes_after_autofix_without_retry(tmp_path: Path) -> None:
    baseline = Candidate(
        id="baseline",
        parent_id=None,
        depth=0,
        workspace=tmp_path / "baseline",
        suggestion_trace=(),
    )
    baseline.workspace.mkdir()
    applier = FlakyApplier()
    feedback_seen: list[str] = []

    def self_check(_: Path) -> tuple[bool, str]:
        if not feedback_seen:
            feedback_seen.append("first")
            return False, "pytest failed"
        return True, ""

    def evaluator(_: Path) -> dict[str, object]:
        return {
            "hard_evaluation": {"all_passed": True},
            "qc_evaluation": {"all_passed": True, "failures": []},
            "soft_evaluation": {"understandability_score": 88.0},
            "final_report": {"verdict": "Pass", "suggestions": []},
        }

    candidate = execute_candidate(
        parent=baseline,
        candidate_id="c1",
        suggestion={
            "title": "Improve readability",
            "description": "Split helper",
            "target_file": "sample.py",
        },
        workspace_root=tmp_path / "runs",
        applier=applier,
        self_check_runner=self_check,
        evaluator_runner=evaluator,
        max_retries=2,
    )

    assert candidate.status == "measured"
    assert applier.calls == [""]
    assert candidate.retry_count == 0


def test_execute_candidate_runs_ruff_fix_before_retrying_llm(tmp_path: Path) -> None:
    baseline = Candidate(
        id="baseline",
        parent_id=None,
        depth=0,
        workspace=tmp_path / "baseline",
        suggestion_trace=(),
    )
    baseline.workspace.mkdir()
    applier = FlakyApplier()
    self_check_calls: list[str] = []
    autofix_calls: list[str] = []
    measured: list[str] = []

    def self_check(workspace: Path) -> tuple[bool, str]:
        self_check_calls.append(workspace.name)
        if len(self_check_calls) == 1:
            return False, "ruff failed"
        return True, ""

    def autofix(workspace: Path) -> tuple[bool, str]:
        autofix_calls.append(workspace.name)
        return True, "fixed"

    def evaluator(workspace: Path) -> dict[str, object]:
        measured.append(workspace.name)
        return {
            "hard_evaluation": {"all_passed": True},
            "qc_evaluation": {"all_passed": True, "failures": []},
            "soft_evaluation": {"understandability_score": 88.0},
            "final_report": {"verdict": "Pass", "suggestions": []},
        }

    candidate = execute_candidate(
        parent=baseline,
        candidate_id="c1",
        suggestion={
            "title": "Improve readability",
            "description": "Split helper",
            "target_file": "sample.py",
        },
        workspace_root=tmp_path / "runs",
        applier=applier,
        self_check_runner=self_check,
        evaluator_runner=evaluator,
        max_retries=2,
        autofix_runner=autofix,
    )

    assert candidate.status == "measured"
    assert candidate.retry_count == 0
    assert applier.calls == [""]
    assert self_check_calls == ["c1", "c1"]
    assert autofix_calls == ["c1"]
    assert measured == ["c1"]


def test_execute_candidate_retries_with_post_fix_feedback_when_autofix_does_not_help(
    tmp_path: Path,
) -> None:
    baseline = Candidate(
        id="baseline",
        parent_id=None,
        depth=0,
        workspace=tmp_path / "baseline",
        suggestion_trace=(),
    )
    baseline.workspace.mkdir()
    applier = FlakyApplier()
    autofix_calls: list[str] = []
    self_check_attempts = 0

    def self_check(_: Path) -> tuple[bool, str]:
        nonlocal self_check_attempts
        self_check_attempts += 1
        if self_check_attempts == 1:
            return False, "ruff failed"
        if self_check_attempts == 2:
            return False, "mypy failed"
        return True, ""

    def autofix(workspace: Path) -> tuple[bool, str]:
        autofix_calls.append(workspace.name)
        return True, "fixed"

    def evaluator(_: Path) -> dict[str, object]:
        return {
            "hard_evaluation": {"all_passed": True},
            "qc_evaluation": {"all_passed": True, "failures": []},
            "soft_evaluation": {"understandability_score": 88.0},
            "final_report": {"verdict": "Pass", "suggestions": []},
        }

    candidate = execute_candidate(
        parent=baseline,
        candidate_id="c1",
        suggestion={
            "title": "Improve readability",
            "description": "Split helper",
            "target_file": "sample.py",
        },
        workspace_root=tmp_path / "runs",
        applier=applier,
        self_check_runner=self_check,
        evaluator_runner=evaluator,
        max_retries=2,
        autofix_runner=autofix,
    )

    assert candidate.status == "measured"
    assert candidate.retry_count == 1
    assert applier.calls[0] == ""
    assert "Structured guardrail failure summary:" in applier.calls[1]
    assert "mypy failed" in applier.calls[1]
    assert autofix_calls == ["c1"]


def test_execute_candidate_stops_early_when_guardrail_failure_stagnates(
    tmp_path: Path,
) -> None:
    baseline = Candidate(
        id="baseline",
        parent_id=None,
        depth=0,
        workspace=tmp_path / "baseline",
        suggestion_trace=(),
    )
    baseline.workspace.mkdir()
    applier = FlakyApplier()

    def self_check(_: Path) -> tuple[bool, str]:
        return (
            False,
            'python_harness/cli.py:107: error: Returning Any from function '
            'declared to return "str"',
        )

    candidate = execute_candidate(
        parent=baseline,
        candidate_id="stalled",
        suggestion={
            "title": "Improve readability",
            "description": "Split helper",
            "target_file": "sample.py",
        },
        workspace_root=tmp_path / "runs",
        applier=applier,
        self_check_runner=self_check,
        evaluator_runner=lambda _: {
            "final_report": {"verdict": "Fail", "suggestions": []}
        },
        max_retries=10,
        autofix_runner=lambda _: (False, "no changes"),
    )

    assert candidate.status == "failed"
    assert candidate.retry_count < 10
    assert "stalled on repeated guardrail failures" in candidate.selection_reason
    assert len(applier.calls) == 3


def test_execute_candidate_does_not_retry_non_retryable_apply_failure(
    tmp_path: Path,
) -> None:
    baseline = Candidate(
        id="baseline",
        parent_id=None,
        depth=0,
        workspace=tmp_path / "baseline",
        suggestion_trace=(),
    )
    baseline.workspace.mkdir()
    applier = NonRetryableFailureApplier()

    candidate = execute_candidate(
        parent=baseline,
        candidate_id="c1",
        suggestion={
            "title": "Improve readability",
            "description": "Split helper",
            "target_file": "sample.py",
        },
        workspace_root=tmp_path / "runs",
        applier=applier,
        self_check_runner=lambda _: (True, ""),
        evaluator_runner=lambda _: {
            "final_report": {"verdict": "Fail", "suggestions": []}
        },
        max_retries=3,
    )

    assert candidate.status == "failed"
    assert candidate.retry_count == 0
    assert applier.calls == 1


def test_execute_candidate_with_default_self_check_does_not_measure_failed_candidate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    baseline = Candidate(
        id="baseline",
        parent_id=None,
        depth=0,
        workspace=tmp_path / "baseline",
        suggestion_trace=(),
    )
    baseline.workspace.mkdir()
    measured: list[str] = []
    commands: list[tuple[list[str], Path]] = []

    def fake_run(
        args: list[str],
        *,
        cwd: Path,
        capture_output: bool,
        text: bool,
        check: bool,
    ) -> SimpleNamespace:
        del capture_output, text, check
        commands.append((args, cwd))
        return SimpleNamespace(returncode=1, stdout="", stderr="ruff failed")

    def evaluator(workspace: Path) -> dict[str, object]:
        measured.append(workspace.name)
        return {"final_report": {"verdict": "Fail", "suggestions": []}}

    monkeypatch.setattr("python_harness.refine_checks.subprocess.run", fake_run)

    candidate = execute_candidate(
        parent=baseline,
        candidate_id="blocked",
        suggestion={
            "title": "Fix tests",
            "description": "d",
            "target_file": "sample.py",
        },
        workspace_root=tmp_path / "runs",
        applier=NullSuggestionApplier(),
        self_check_runner=refine_checks.default_self_check_runner,
        evaluator_runner=evaluator,
        max_retries=0,
    )

    expected_workspace = tmp_path / "runs" / "blocked"
    assert candidate.status == "failed"
    assert measured == []
    assert commands == [
        (
            [sys.executable, "-m", "ruff", "check", str(expected_workspace)],
            expected_workspace,
        ),
        (
            [
                sys.executable,
                "-m",
                "ruff",
                "check",
                "--fix",
                str(expected_workspace),
            ],
            expected_workspace,
        ),
        (
            [sys.executable, "-m", "ruff", "check", str(expected_workspace)],
            expected_workspace,
        ),
    ]


def test_default_self_check_runner_uses_target_path_in_all_commands(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "sample.py").write_text("print('ok')\n")
    calls: list[tuple[list[str], Path]] = []

    def fake_run(
        args: list[str],
        *,
        cwd: Path,
        capture_output: bool,
        text: bool,
        check: bool,
    ) -> SimpleNamespace:
        del capture_output, text, check
        calls.append((args, cwd))
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr("python_harness.refine_checks.subprocess.run", fake_run)

    ok, output = refine_checks.default_self_check_runner(workspace)

    assert ok is True
    assert output == ""
    assert calls == [
        ([sys.executable, "-m", "ruff", "check", str(workspace)], workspace),
        ([sys.executable, "-m", "mypy", str(workspace)], workspace),
        ([sys.executable, "-m", "pytest", str(workspace)], workspace),
    ]


def test_execute_candidate_retries_when_applier_returns_not_ok(tmp_path: Path) -> None:
    baseline = Candidate(
        id="baseline",
        parent_id=None,
        depth=0,
        workspace=tmp_path / "baseline",
        suggestion_trace=(),
    )
    baseline.workspace.mkdir()
    feedback_seen: list[str] = []
    measure_calls: list[str] = []

    class RetryApplier:
        def __init__(self) -> None:
            self.calls = 0

        def apply(
            self,
            workspace: Path,
            suggestion: dict[str, str],
            failure_feedback: str = "",
        ) -> dict[str, object]:
            del workspace, suggestion
            feedback_seen.append(failure_feedback)
            self.calls += 1
            if self.calls == 1:
                return {
                    "ok": False,
                    "touched_files": [],
                    "failure_reason": "model refused patch",
                }
            return {"ok": True, "touched_files": [], "failure_reason": ""}

    def evaluator(workspace: Path) -> dict[str, object]:
        measure_calls.append(workspace.name)
        return {
            "hard_evaluation": {"all_passed": True},
            "qc_evaluation": {"all_passed": True, "failures": []},
            "soft_evaluation": {"understandability_score": 88.0},
            "final_report": {"verdict": "Pass", "suggestions": []},
        }

    candidate = execute_candidate(
        parent=baseline,
        candidate_id="retry-ok-false",
        suggestion={
            "title": "Retry patch",
            "description": "d",
            "target_file": "sample.py",
        },
        workspace_root=tmp_path / "runs",
        applier=RetryApplier(),
        self_check_runner=lambda _: (True, ""),
        evaluator_runner=evaluator,
        max_retries=1,
    )

    assert candidate.status == "measured"
    assert candidate.retry_count == 1
    assert feedback_seen == ["", "model refused patch"]
    assert measure_calls == ["retry-ok-false"]


def test_execute_candidate_retries_when_applier_raises(tmp_path: Path) -> None:
    baseline = Candidate(
        id="baseline",
        parent_id=None,
        depth=0,
        workspace=tmp_path / "baseline",
        suggestion_trace=(),
    )
    baseline.workspace.mkdir()
    feedback_seen: list[str] = []
    evaluated: list[str] = []

    class ExplodingApplier:
        def __init__(self) -> None:
            self.calls = 0

        def apply(
            self,
            workspace: Path,
            suggestion: dict[str, str],
            failure_feedback: str = "",
        ) -> dict[str, object]:
            del workspace, suggestion
            feedback_seen.append(failure_feedback)
            self.calls += 1
            raise RuntimeError(f"boom {self.calls}")

    def evaluator(workspace: Path) -> dict[str, object]:
        evaluated.append(workspace.name)
        return {"final_report": {"verdict": "Pass", "suggestions": []}}

    candidate = execute_candidate(
        parent=baseline,
        candidate_id="retry-exception",
        suggestion={
            "title": "Retry exception",
            "description": "d",
            "target_file": "sample.py",
        },
        workspace_root=tmp_path / "runs",
        applier=ExplodingApplier(),
        self_check_runner=lambda _: (True, ""),
        evaluator_runner=evaluator,
        max_retries=1,
    )

    assert candidate.status == "failed"
    assert candidate.retry_count == 1
    assert candidate.selection_reason == "boom 2"
    assert feedback_seen == ["", "boom 1"]
    assert evaluated == []


def test_run_refine_round_creates_three_first_layer_and_nine_second_layer(
    tmp_path: Path,
) -> None:
    target = tmp_path / "baseline"
    target.mkdir()
    (target / "sample.py").write_text("print('baseline')\n")

    def evaluator(workspace: Path) -> dict[str, object]:
        name = workspace.name
        if name == "baseline":
            return {
                "hard_evaluation": {"all_passed": True},
                "qc_evaluation": {"all_passed": True, "failures": []},
                "soft_evaluation": {"understandability_score": 80.0},
                "final_report": {
                    "verdict": "Fail",
                    "suggestions": [
                        {
                            "title": "S1",
                            "description": "d1",
                            "target_file": "sample.py",
                        },
                        {
                            "title": "S2",
                            "description": "d2",
                            "target_file": "sample.py",
                        },
                        {
                            "title": "S3",
                            "description": "d3",
                            "target_file": "sample.py",
                        },
                    ],
                },
            }
        if name.startswith("l1-"):
            return {
                "hard_evaluation": {"all_passed": True},
                "qc_evaluation": {"all_passed": True, "failures": []},
                "soft_evaluation": {"understandability_score": 82.0},
                "final_report": {
                    "verdict": "Fail",
                    "suggestions": [
                        {
                            "title": f"{name}-A",
                            "description": "x",
                            "target_file": "sample.py",
                        },
                        {
                            "title": f"{name}-B",
                            "description": "x",
                            "target_file": "sample.py",
                        },
                        {
                            "title": f"{name}-C",
                            "description": "x",
                            "target_file": "sample.py",
                        },
                    ],
                },
            }
        return {
            "hard_evaluation": {"all_passed": True},
            "qc_evaluation": {"all_passed": True, "failures": []},
            "soft_evaluation": {"understandability_score": 90.0},
            "final_report": {"verdict": "Pass", "suggestions": []},
        }

    result = run_refine_round(
        target_path=target,
        workspace_root=tmp_path / "runs",
        evaluator_runner=evaluator,
        applier=StaticSuccessApplier(),
        self_check_runner=lambda _: (True, ""),
        max_retries=0,
    )

    assert result.baseline.id == "baseline"
    first_layer = [
        candidate for candidate in result.candidates if candidate.depth == 1
    ]
    second_layer = [
        candidate for candidate in result.candidates if candidate.depth == 2
    ]
    assert len(first_layer) == 3
    assert len(second_layer) == 9


def test_run_refine_round_stops_early_without_real_suggestion_applier(
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


def test_run_refine_round_limits_suggestions_to_top_three(tmp_path: Path) -> None:
    target = tmp_path / "baseline"
    target.mkdir()
    (target / "sample.py").write_text("print('baseline')\n")

    def evaluator(workspace: Path) -> dict[str, object]:
        name = workspace.name
        if name == "baseline":
            return {
                "hard_evaluation": {"all_passed": True},
                "qc_evaluation": {"all_passed": True, "failures": []},
                "soft_evaluation": {"understandability_score": 80.0},
                "final_report": {
                    "verdict": "Fail",
                    "suggestions": [
                        {
                            "title": "S1",
                            "description": "d1",
                            "target_file": "sample.py",
                        },
                        {
                            "title": "S2",
                            "description": "d2",
                            "target_file": "sample.py",
                        },
                        {
                            "title": "S3",
                            "description": "d3",
                            "target_file": "sample.py",
                        },
                        {
                            "title": "S4",
                            "description": "d4",
                            "target_file": "sample.py",
                        },
                    ],
                },
            }
        if name.startswith("l1-"):
            return {
                "hard_evaluation": {"all_passed": True},
                "qc_evaluation": {"all_passed": True, "failures": []},
                "soft_evaluation": {"understandability_score": 82.0},
                "final_report": {
                    "verdict": "Fail",
                    "suggestions": [
                        {
                            "title": f"{name}-A",
                            "description": "x",
                            "target_file": "sample.py",
                        },
                        {
                            "title": f"{name}-B",
                            "description": "x",
                            "target_file": "sample.py",
                        },
                        {
                            "title": f"{name}-C",
                            "description": "x",
                            "target_file": "sample.py",
                        },
                        {
                            "title": f"{name}-D",
                            "description": "x",
                            "target_file": "sample.py",
                        },
                    ],
                },
            }
        return {
            "hard_evaluation": {"all_passed": True},
            "qc_evaluation": {"all_passed": True, "failures": []},
            "soft_evaluation": {"understandability_score": 90.0},
            "final_report": {"verdict": "Pass", "suggestions": []},
        }

    result = run_refine_round(
        target_path=target,
        workspace_root=tmp_path / "runs",
        evaluator_runner=evaluator,
        applier=StaticSuccessApplier(),
        self_check_runner=lambda _: (True, ""),
        max_retries=0,
    )

    first_layer_ids = [
        candidate.id for candidate in result.candidates if candidate.depth == 1
    ]
    second_layer = [
        candidate for candidate in result.candidates if candidate.depth == 2
    ]

    assert first_layer_ids == ["l1-1", "l1-2", "l1-3"]
    assert len(second_layer) == 9


def test_suggestions_from_requires_specific_target_file() -> None:
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


def test_run_refine_stops_when_winner_has_no_suggestions(tmp_path: Path) -> None:
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


def test_run_refine_stops_early_without_real_suggestion_applier(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    target = tmp_path / "target"
    target.mkdir()
    (target / "sample.py").write_text("print('baseline')\n")
    monkeypatch.delenv("LLM_API_KEY", raising=False)

    def evaluator(_: Path) -> dict[str, object]:
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

    result = run_refine(
        target_path=target,
        max_retries=0,
        loop=True,
        max_rounds=3,
        evaluator_runner=evaluator,
    )

    assert result["rounds_completed"] == 1
    assert result["winner_id"] == "baseline"
    assert result["stop_reason"] == "no suggestion applier configured"


def test_run_refine_uses_real_llm_applier_when_api_key_present(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    target = tmp_path / "target"
    target.mkdir()
    (target / "sample.py").write_text("print('baseline')\n")
    monkeypatch.setenv("LLM_API_KEY", "test-key")
    monkeypatch.setattr(
        "python_harness.refine_rounds.LLMSuggestionApplier",
        lambda: StaticSuccessApplier(),
    )

    result = run_refine(
        target_path=target,
        max_retries=0,
        loop=True,
        max_rounds=3,
        evaluator_runner=lambda _: {
            "hard_evaluation": {"all_passed": True},
            "qc_evaluation": {"all_passed": True, "failures": []},
            "soft_evaluation": {"understandability_score": 80.0},
            "final_report": {"verdict": "Fail", "suggestions": []},
        },
    )

    assert result["stop_reason"] != "no suggestion applier configured"


def test_run_refine_adopts_winner_workspace_and_stops_without_improvement(
    tmp_path: Path,
) -> None:
    target = tmp_path / "target"
    target.mkdir()
    (target / "sample.py").write_text("baseline\n")

    def evaluator(workspace: Path) -> dict[str, object]:
        if (workspace / "sample.py").read_text() == "baseline\n":
            return {
                "hard_evaluation": {"all_passed": True},
                "qc_evaluation": {"all_passed": True, "failures": []},
                "soft_evaluation": {
                    "understandability_score": 70.0,
                    "package_summary": {"total_tokens": 11},
                },
                "final_report": {
                    "verdict": "Fail",
                    "suggestions": [
                        {
                            "title": "Winner",
                            "description": "Apply better layout",
                            "target_file": "sample.py",
                        },
                    ],
                },
                "metrics": {
                    "avg_mi": 60.0,
                    "qa_score": 70.0,
                    "cc_issue_count": 1,
                    "hard_failed": False,
                    "qc_failed": False,
                },
            }
        return {
            "hard_evaluation": {"all_passed": True},
            "qc_evaluation": {"all_passed": True, "failures": []},
            "soft_evaluation": {"understandability_score": 95.0},
            "final_report": {
                "verdict": "Pass",
                "suggestions": [
                        {
                            "title": "Keep polishing",
                            "description": "Still possible",
                            "target_file": "sample.py",
                        }
                ],
            },
            "metrics": {
                "avg_mi": 90.0,
                "qa_score": 95.0,
                "cc_issue_count": 0,
                "hard_failed": False,
                "qc_failed": False,
            },
        }

    class StaticApplier:
        def apply(
            self,
            workspace: Path,
            suggestion: dict[str, str],
            failure_feedback: str = "",
        ) -> dict[str, object]:
            del failure_feedback
            (workspace / "sample.py").write_text(f"{suggestion['title']}\n")
            return {"ok": True, "touched_files": ["sample.py"], "failure_reason": ""}

    result = run_refine(
        target_path=target,
        max_retries=0,
        loop=True,
        max_rounds=3,
        evaluator_runner=evaluator,
        applier=StaticApplier(),
        self_check_runner=lambda _: (True, ""),
    )

    assert result["rounds_completed"] == 2
    assert result["winner_id"] == "baseline"
    assert result["stop_reason"] == "winner did not improve baseline"
    assert (target / "sample.py").read_text() == "Winner\n"


def test_run_refine_accepts_direct_child_workspace_root(tmp_path: Path) -> None:
    target = tmp_path / "target"
    target.mkdir()
    (target / "sample.py").write_text("print('baseline')\n")

    result = run_refine(
        target_path=target,
        workspace_root=target / ".harness-refine",
        max_retries=0,
        loop=False,
        max_rounds=1,
        evaluator_runner=lambda _: {
            "hard_evaluation": {"all_passed": True},
            "qc_evaluation": {"all_passed": True, "failures": []},
            "soft_evaluation": {"understandability_score": 80.0},
            "final_report": {"verdict": "Fail", "suggestions": []},
        },
    )

    assert result["stop_reason"] == "single round completed"


def test_run_refine_emits_guardrail_stage_logs(tmp_path: Path) -> None:
    target = tmp_path / "target"
    target.mkdir()
    (target / "sample.py").write_text("baseline\n")
    messages: list[str] = []

    def evaluator(workspace: Path) -> dict[str, object]:
        if workspace == target:
            return {
                "hard_evaluation": {"all_passed": True},
                "qc_evaluation": {"all_passed": True, "failures": []},
                "soft_evaluation": {
                    "understandability_score": 70.0,
                    "package_summary": {"total_tokens": 11},
                },
                "final_report": {
                    "verdict": "Fail",
                    "suggestions": [
                        {
                            "title": "Winner",
                            "description": "Apply better layout",
                            "target_file": "sample.py",
                        },
                    ],
                },
            }
        return {
            "hard_evaluation": {"all_passed": True},
            "qc_evaluation": {"all_passed": True, "failures": []},
            "soft_evaluation": {"understandability_score": 95.0},
            "final_report": {"verdict": "Pass", "suggestions": []},
        }

    class StaticApplier:
        def apply(
            self,
            workspace: Path,
            suggestion: dict[str, str],
            failure_feedback: str = "",
        ) -> dict[str, object]:
            del failure_feedback
            (workspace / "sample.py").write_text(f"{suggestion['title']}\n")
            return {"ok": True, "touched_files": ["sample.py"], "failure_reason": ""}

    run_refine(
        target_path=target,
        max_retries=0,
        loop=False,
        max_rounds=1,
        evaluator_runner=evaluator,
        applier=StaticApplier(),
        self_check_runner=lambda _: (True, ""),
        progress_callback=messages.append,
    )

    assert any("baseline measure started" in message for message in messages)
    assert any("l1-1 apply started" in message for message in messages)
    assert any("l1-1 guardrail 1 passed" in message for message in messages)
    assert any("l1-1 guardrail 2 started" in message for message in messages)


def test_run_refine_emits_failure_detail_for_guardrail_failure(tmp_path: Path) -> None:
    target = tmp_path / "target"
    target.mkdir()
    (target / "sample.py").write_text("baseline\n")
    messages: list[str] = []

    class StaticApplier:
        def apply(
            self,
            workspace: Path,
            suggestion: dict[str, str],
            failure_feedback: str = "",
        ) -> dict[str, object]:
            del workspace, suggestion, failure_feedback
            return {"ok": True, "touched_files": [], "failure_reason": ""}

    run_refine(
        target_path=target,
        max_retries=0,
        loop=False,
        max_rounds=1,
        evaluator_runner=lambda _: {
            "hard_evaluation": {"all_passed": True},
            "qc_evaluation": {"all_passed": True, "failures": []},
            "soft_evaluation": {"understandability_score": 70.0},
            "final_report": {
                "verdict": "Fail",
                "suggestions": [
                    {
                        "title": "Winner",
                        "description": "Apply better layout",
                        "target_file": "sample.py",
                    },
                ],
            },
        },
        applier=StaticApplier(),
        self_check_runner=lambda _: (False, "ruff failed"),
        progress_callback=messages.append,
    )

    assert any("guardrail 1 failed" in message for message in messages)
    assert any("ruff failed" in message for message in messages)


def test_run_refine_emits_candidate_measure_and_selection_logs(
    tmp_path: Path,
) -> None:
    target = tmp_path / "target"
    target.mkdir()
    (target / "sample.py").write_text("baseline\n")
    messages: list[str] = []

    def evaluator(workspace: Path) -> dict[str, object]:
        if workspace == target:
            return {
                "hard_evaluation": {"all_passed": True},
                "qc_evaluation": {"all_passed": True, "failures": []},
                "soft_evaluation": {
                    "understandability_score": 70.0,
                    "package_summary": {"total_tokens": 11},
                },
                "final_report": {
                    "verdict": "Fail",
                    "suggestions": [
                        {
                            "title": "Winner",
                            "description": "Apply better layout",
                            "target_file": "sample.py",
                        },
                    ],
                },
                "metrics": {
                    "avg_mi": 60.0,
                    "qa_score": 70.0,
                    "cc_issue_count": 1,
                    "hard_failed": False,
                    "qc_failed": False,
                },
            }
        return {
            "hard_evaluation": {"all_passed": True},
            "qc_evaluation": {"all_passed": True, "failures": []},
            "soft_evaluation": {
                "understandability_score": 95.0,
                "package_summary": {"total_tokens": 22},
            },
            "final_report": {"verdict": "Pass", "suggestions": []},
            "metrics": {
                "avg_mi": 90.0,
                "qa_score": 95.0,
                "cc_issue_count": 0,
                "hard_failed": False,
                "qc_failed": False,
            },
        }

    class StaticApplier:
        def apply(
            self,
            workspace: Path,
            suggestion: dict[str, str],
            failure_feedback: str = "",
        ) -> dict[str, object]:
            del failure_feedback
            (workspace / "sample.py").write_text(f"{suggestion['title']}\n")
            return {"ok": True, "touched_files": ["sample.py"], "failure_reason": ""}

    run_refine(
        target_path=target,
        max_retries=0,
        loop=False,
        max_rounds=1,
        evaluator_runner=evaluator,
        applier=StaticApplier(),
        self_check_runner=lambda _: (True, ""),
        progress_callback=messages.append,
    )

    assert any("candidate 1/1 started: l1-1" in message for message in messages)
    assert any(
        "candidate 1/1 completed: l1-1 (measured)" in message
        for message in messages
    )
    assert any("l1-1 guardrail 2 completed" in message for message in messages)
    assert any("round 1 selection winner: l1-1" in message for message in messages)
    assert any(
        "round 1 adopted winner workspace: l1-1" in message
        for message in messages
    )
    assert any("round 1 scorecard:" in message for message in messages)
    assert any(
        "baseline | status=measured | loc=1 | tokens=11 | "
        "readability=70.0 | hard=pass | qc=pass | mi=60.0 | qa=70.0"
        in message
        for message in messages
    )
    assert any(
        "l1-1 | status=measured | loc=1 | tokens=22 | "
        "readability=95.0 | hard=pass | qc=pass | mi=90.0 | qa=95.0"
        in message
        for message in messages
    )
    assert any(
        "round 1 winner reason: l1-1 beats baseline"
        in message
        for message in messages
    )


def test_run_refine_emits_baseline_guardrail_logs(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    target = tmp_path / "target"
    target.mkdir()
    (target / "sample.py").write_text("baseline\n")
    messages: list[str] = []

    class DummyHardEvaluator:
        def __init__(self, target_path: str) -> None:
            self.target_path = target_path

        def evaluate(self) -> dict[str, object]:
            assert self.target_path == str(target)
            return {"all_passed": True}

    class DummyQCEvaluator:
        def __init__(self, target_path: str) -> None:
            self.target_path = target_path

        def evaluate(self) -> dict[str, object]:
            assert self.target_path == str(target)
            return {"all_passed": True, "failures": []}

    class DummySoftEvaluator:
        def __init__(self, target_path: str) -> None:
            self.target_path = target_path

        def evaluate(self) -> dict[str, object]:
            assert self.target_path == str(target)
            return {
                "understandability_score": 80.0,
                "qa_results": {"sampled_entities": []},
            }

        def generate_final_report(
            self,
            hard_results: dict[str, object],
            qc_results: dict[str, object],
            soft_results: dict[str, object],
        ) -> dict[str, object]:
            del hard_results, qc_results, soft_results
            return {"verdict": "Fail", "suggestions": []}

    monkeypatch.setattr(
        "python_harness.refine_rounds.HardEvaluator",
        DummyHardEvaluator,
    )
    monkeypatch.setattr("python_harness.refine_rounds.QCEvaluator", DummyQCEvaluator)
    monkeypatch.setattr(
        "python_harness.refine_rounds.SoftEvaluator",
        DummySoftEvaluator,
    )

    run_refine(
        target_path=target,
        max_retries=0,
        loop=False,
        max_rounds=1,
        progress_callback=messages.append,
    )

    assert any("baseline guardrail 1 started" in message for message in messages)
    assert any("baseline guardrail 1 passed" in message for message in messages)
    assert any("baseline guardrail 2 started" in message for message in messages)
    assert any("baseline guardrail 2 passed" in message for message in messages)


def test_run_refine_persists_round_artifact(tmp_path: Path) -> None:
    target = tmp_path / "target"
    target.mkdir()
    (target / "sample.py").write_text("baseline\n")
    workspace_root = tmp_path / "runs"

    def evaluator(workspace: Path) -> dict[str, object]:
        if workspace == target:
            return {
                "hard_evaluation": {"all_passed": True},
                "qc_evaluation": {"all_passed": True, "failures": []},
                "soft_evaluation": {
                    "understandability_score": 70.0,
                    "package_summary": {"total_tokens": 11},
                },
                "final_report": {
                    "verdict": "Fail",
                    "suggestions": [
                        {
                            "title": "Winner",
                            "description": "Apply better layout",
                            "target_file": "sample.py",
                        }
                    ],
                },
                "metrics": {
                    "avg_mi": 60.0,
                    "qa_score": 70.0,
                    "cc_issue_count": 1,
                    "hard_failed": False,
                    "qc_failed": False,
                },
            }
        return {
            "hard_evaluation": {"all_passed": True},
            "qc_evaluation": {"all_passed": True, "failures": []},
            "soft_evaluation": {
                "understandability_score": 95.0,
                "package_summary": {"total_tokens": 22},
            },
            "final_report": {"verdict": "Pass", "suggestions": []},
            "metrics": {
                "avg_mi": 90.0,
                "qa_score": 95.0,
                "cc_issue_count": 0,
                "hard_failed": False,
                "qc_failed": False,
            },
        }

    class StaticApplier:
        def apply(
            self,
            workspace: Path,
            suggestion: dict[str, str],
            failure_feedback: str = "",
        ) -> dict[str, object]:
            del failure_feedback
            (workspace / "sample.py").write_text(f"{suggestion['title']}\n")
            return {"ok": True, "touched_files": ["sample.py"], "failure_reason": ""}

    run_refine(
        target_path=target,
        workspace_root=workspace_root,
        max_retries=0,
        loop=False,
        max_rounds=1,
        evaluator_runner=evaluator,
        applier=StaticApplier(),
        self_check_runner=lambda _: (True, ""),
    )

    artifact_path = workspace_root / "artifacts" / "round-001.json"
    artifact = json.loads(artifact_path.read_text())
    assert artifact["round"] == 1
    assert artifact["winner_id"] == "l1-1"
    assert artifact["stop_reason"] == "single round completed"
    assert artifact["baseline"]["scorecard"].startswith("baseline | status=measured")
    assert artifact["candidates"][0]["suggestion"]["target_file"] == "sample.py"


def test_run_refine_rejects_nested_workspace_root_inside_target(tmp_path: Path) -> None:
    target = tmp_path / "target"
    nested = target / "nested" / ".harness-refine"
    target.mkdir()
    (target / "sample.py").write_text("print('baseline')\n")

    with pytest.raises(ValueError, match="workspace_root"):
        run_refine(
            target_path=target,
            workspace_root=nested,
            max_retries=0,
            loop=False,
            max_rounds=1,
            evaluator_runner=lambda _: {
                "hard_evaluation": {"all_passed": True},
                "qc_evaluation": {"all_passed": True, "failures": []},
                "soft_evaluation": {"understandability_score": 80.0},
                "final_report": {"verdict": "Fail", "suggestions": []},
            },
        )
