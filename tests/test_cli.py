"""
Tests for CLI functionality.
"""

from pathlib import Path
from typing import Any

from typer.testing import CliRunner

import python_harness.cli as cli_module
from python_harness.cli import app

runner = CliRunner()


def test_measure_command(monkeypatch: Any) -> None:
    """
    Test the 'measure' command.
    """
    class DummyHardEvaluator:
        def evaluate(self) -> dict[str, Any]:
            return {
                "all_passed": True,
                "ruff": {"status": "success", "issues": []},
                "mypy": {"status": "success", "output": ""},
                "ty": {"status": "success", "output": ""},
                "radon_cc": {"status": "success", "issues": [], "error_message": ""},
                "radon_mi": {"status": "success", "mi_scores": {}},
                "pytest": {"status": "success", "output": ""},
            }

    class DummyQcEvaluator:
        def evaluate(self) -> dict[str, Any]:
            return {"all_passed": True, "failures": []}

    class DummySoftEvaluator:
        def evaluate(self) -> dict[str, Any]:
            return {
                "package_summary": {
                    "total_files": 1,
                    "total_tokens": 1,
                    "package_understanding": "Mock understanding",
                },
                "understandability_score": 100.0,
                "qa_results": {"sampled_entities": []},
            }

        def generate_final_report(
            self,
            hard_results: dict[str, Any],
            qc_results: dict[str, Any],
            soft_results: dict[str, Any],
        ) -> dict[str, Any]:
            return {"verdict": "Pass", "summary": "Mock summary", "suggestions": []}

    class DummyEvaluator:
        def __init__(self, path: str):
            self.path = path
            self.hard_evaluator = DummyHardEvaluator()
            self.qc_evaluator = DummyQcEvaluator()
            self.soft_evaluator = DummySoftEvaluator()

    monkeypatch.setattr(cli_module, "Evaluator", DummyEvaluator)

    result = runner.invoke(app, ["measure", "."])

    assert result.exit_code == 0
    assert "Starting harness measurement" in result.stdout


def test_measure_formats_hard_failures_consistently(monkeypatch: Any) -> None:
    """
    Test that hard evaluation failures are rendered as consistent sections.
    """
    class DummyHardEvaluator:
        def evaluate(self) -> dict[str, Any]:
            return {
                "all_passed": False,
                "ruff": {"status": "success", "issues": []},
                "mypy": {"status": "success", "output": ""},
                "ty": {
                    "status": "warning",
                    "error_message": "ty executable not found. Skipping ty checks.",
                },
                "radon_cc": {
                    "status": "warning",
                    "issues": [],
                    "error_message": "radon executable not found. Please install it.",
                },
                "radon_mi": {"status": "success", "mi_scores": {}},
                "pytest": {"status": "failed", "error_message": "Tests failed"},
            }

    class DummyQcEvaluator:
        def evaluate(self) -> dict[str, Any]:
            return {"all_passed": True, "failures": []}

    class DummySoftEvaluator:
        def evaluate(self) -> dict[str, Any]:
            return {
                "package_summary": {
                    "total_files": 1,
                    "total_tokens": 1,
                    "package_understanding": "Mock understanding",
                },
                "understandability_score": 75.0,
                "qa_results": {"sampled_entities": []},
            }

        def generate_final_report(
            self,
            hard_results: dict[str, Any],
            qc_results: dict[str, Any],
            soft_results: dict[str, Any],
        ) -> dict[str, Any]:
            return {"verdict": "Fail", "summary": "Mock summary", "suggestions": []}

    class DummyEvaluator:
        def __init__(self, path: str):
            self.path = path
            self.hard_evaluator = DummyHardEvaluator()
            self.qc_evaluator = DummyQcEvaluator()
            self.soft_evaluator = DummySoftEvaluator()

    monkeypatch.setattr(cli_module, "Evaluator", DummyEvaluator)

    result = runner.invoke(app, ["measure", "."])

    assert result.exit_code == 1
    assert "Hard Evaluation Failed!" in result.stdout
    assert "Exiting." not in result.stdout
    assert (
        "Ty warning:\n  ty executable not found. Skipping ty checks."
        in result.stdout
    )
    assert (
        "Radon CC warning:\n  radon executable not found. Please install it."
        in result.stdout
    )
    assert "Pytest/Coverage issues found:\n  Tests failed" in result.stdout
    assert "Cyclomatic Complexity too high (0 functions > 15):" not in result.stdout
    assert "\n\n\n" not in result.stdout


def test_measure_prints_soft_evaluation_header_before_agent_logs(
    monkeypatch: Any,
) -> None:
    """
    Test that the soft evaluation section header appears before evaluator progress logs.
    """
    class DummyHardEvaluator:
        def evaluate(self) -> dict[str, Any]:
            return {
                "all_passed": True,
                "ruff": {"status": "success", "issues": []},
                "mypy": {"status": "success", "output": ""},
                "ty": {"status": "success", "output": ""},
                "radon_cc": {"status": "success", "issues": [], "error_message": ""},
                "radon_mi": {"status": "success", "mi_scores": {}},
                "pytest": {"status": "success", "output": ""},
            }

    class DummyQcEvaluator:
        def evaluate(self) -> dict[str, Any]:
            return {"all_passed": True, "failures": []}

    class DummySoftEvaluator:
        def evaluate(self) -> dict[str, Any]:
            cli_module.console.print(
                "[cyan]Agent is analyzing 1 Python files...[/cyan]"
            )
            cli_module.console.print(
                "[cyan]Agent is synthesizing global package architecture...[/cyan]"
            )
            return {
                "package_summary": {
                    "total_files": 1,
                    "total_tokens": 1,
                    "package_understanding": "Mock understanding",
                },
                "understandability_score": 100.0,
                "qa_results": {"sampled_entities": []},
            }

        def generate_final_report(
            self,
            hard_results: dict[str, Any],
            qc_results: dict[str, Any],
            soft_results: dict[str, Any],
        ) -> dict[str, Any]:
            return {"verdict": "Pass", "summary": "Mock summary", "suggestions": []}

    class DummyEvaluator:
        def __init__(self, path: str):
            self.path = path
            self.hard_evaluator = DummyHardEvaluator()
            self.qc_evaluator = DummyQcEvaluator()
            self.soft_evaluator = DummySoftEvaluator()

    monkeypatch.setattr(cli_module, "Evaluator", DummyEvaluator)

    result = runner.invoke(app, ["measure", "."])

    header_index = result.stdout.index("Running Soft Evaluation")
    progress_index = result.stdout.index("Agent is analyzing 1 Python files")
    assert header_index < progress_index


def test_measure_renders_full_failure_details(monkeypatch: Any) -> None:
    """
    Test that measure renders hard, QC, QA, and suggestion details together.
    """
    class DummyHardEvaluator:
        def evaluate(self) -> dict[str, Any]:
            return {
                "all_passed": False,
                "ruff": {
                    "status": "failed",
                    "issues": [
                        {
                            "filename": "bad.py",
                            "location": {"row": 7},
                            "message": "boom",
                        }
                    ],
                },
                "mypy": {"status": "failed", "output": "bad.py:1: error: nope"},
                "ty": {"status": "failed", "error_message": "ty exploded"},
                "radon_cc": {
                    "status": "failed",
                    "issues": [
                        {
                            "file": "bad.py",
                            "type": "function",
                            "name": "boom",
                            "complexity": 18,
                        }
                    ],
                    "error_message": "",
                },
                "radon_mi": {"status": "success", "mi_scores": {"bad.py": 10.0}},
                "pytest": {"status": "failed", "error_message": "coverage too low"},
            }

    class DummyQcEvaluator:
        def evaluate(self) -> dict[str, Any]:
            return {"all_passed": False, "failures": ["missing evidence"]}

    class DummySoftEvaluator:
        def evaluate(self) -> dict[str, Any]:
            return {
                "package_summary": {
                    "total_files": 2,
                    "total_tokens": 20,
                    "package_understanding": "Mock understanding",
                },
                "understandability_score": 70.0,
                "qa_results": {
                    "sampled_entities": [
                        {
                            "entity": "Function boom (from bad.py)",
                            "score": 60.0,
                            "feedback": "Needs work",
                        }
                    ]
                },
            }

        def generate_final_report(
            self,
            hard_results: dict[str, Any],
            qc_results: dict[str, Any],
            soft_results: dict[str, Any],
        ) -> dict[str, Any]:
            return {
                "verdict": "Fail",
                "summary": "Mock summary",
                "suggestions": [
                    {
                        "title": "Fix tests",
                        "description": "Raise coverage",
                        "target_file": "tests",
                    }
                ],
            }

    class DummyEvaluator:
        def __init__(self, path: str):
            self.path = path
            self.hard_evaluator = DummyHardEvaluator()
            self.qc_evaluator = DummyQcEvaluator()
            self.soft_evaluator = DummySoftEvaluator()

    monkeypatch.setattr(cli_module, "Evaluator", DummyEvaluator)

    result = runner.invoke(app, ["measure", "."])

    assert result.exit_code == 1
    assert "Ruff issues found" in result.stdout
    assert "bad.py:7 boom" in result.stdout
    assert "Mypy issues found" in result.stdout
    assert "Ty error" in result.stdout
    assert "Cyclomatic Complexity too high" in result.stdout
    assert "Governance QC Failed!" in result.stdout
    assert "Blind QA Sampling Results" in result.stdout
    assert "Top 3 Improvement Suggestions" in result.stdout


def test_measure_limits_rendered_suggestions_to_top_three(monkeypatch: Any) -> None:
    class DummyHardEvaluator:
        def evaluate(self) -> dict[str, Any]:
            return {
                "all_passed": True,
                "ruff": {"status": "success", "issues": []},
                "mypy": {"status": "success", "output": ""},
                "ty": {"status": "success", "output": ""},
                "radon_cc": {"status": "success", "issues": [], "error_message": ""},
                "radon_mi": {"status": "success", "mi_scores": {}},
                "pytest": {"status": "success", "output": ""},
            }

    class DummyQcEvaluator:
        def evaluate(self) -> dict[str, Any]:
            return {"all_passed": True, "failures": []}

    class DummySoftEvaluator:
        def evaluate(self) -> dict[str, Any]:
            return {
                "package_summary": {
                    "total_files": 1,
                    "total_tokens": 1,
                    "package_understanding": "Mock understanding",
                },
                "understandability_score": 100.0,
                "qa_results": {"sampled_entities": []},
            }

        def generate_final_report(
            self,
            hard_results: dict[str, Any],
            qc_results: dict[str, Any],
            soft_results: dict[str, Any],
        ) -> dict[str, Any]:
            return {
                "verdict": "Pass",
                "summary": "Mock summary",
                "suggestions": [
                    {"title": "S1", "description": "d1", "target_file": "a.py"},
                    {"title": "S2", "description": "d2", "target_file": "b.py"},
                    {"title": "S3", "description": "d3", "target_file": "c.py"},
                    {"title": "S4", "description": "d4", "target_file": "d.py"},
                ],
            }

    class DummyEvaluator:
        def __init__(self, path: str):
            self.path = path
            self.hard_evaluator = DummyHardEvaluator()
            self.qc_evaluator = DummyQcEvaluator()
            self.soft_evaluator = DummySoftEvaluator()

    monkeypatch.setattr(cli_module, "Evaluator", DummyEvaluator)

    result = runner.invoke(app, ["measure", "."])

    assert result.exit_code == 0
    assert "S1" in result.stdout
    assert "S2" in result.stdout
    assert "S3" in result.stdout
    assert "S4" not in result.stdout


def test_measure_returns_when_final_report_missing(monkeypatch: Any) -> None:
    """
    Test that measure returns cleanly when final report generation is empty.
    """
    class DummyHardEvaluator:
        def evaluate(self) -> dict[str, Any]:
            return {
                "all_passed": True,
                "ruff": {"status": "success", "issues": []},
                "mypy": {"status": "success", "output": ""},
                "ty": {"status": "success", "output": ""},
                "radon_cc": {"status": "success", "issues": [], "error_message": ""},
                "radon_mi": {"status": "success", "mi_scores": {}},
                "pytest": {"status": "success", "output": ""},
            }

    class DummyQcEvaluator:
        def evaluate(self) -> dict[str, Any]:
            return {"all_passed": True, "failures": []}

    class DummySoftEvaluator:
        def evaluate(self) -> dict[str, Any]:
            return {
                "package_summary": {
                    "total_files": 1,
                    "total_tokens": 1,
                    "package_understanding": "Mock understanding",
                },
                "understandability_score": 100.0,
                "qa_results": {"sampled_entities": []},
            }

        def generate_final_report(
            self,
            hard_results: dict[str, Any],
            qc_results: dict[str, Any],
            soft_results: dict[str, Any],
        ) -> dict[str, Any]:
            return {}

    class DummyEvaluator:
        def __init__(self, path: str):
            self.path = path
            self.hard_evaluator = DummyHardEvaluator()
            self.qc_evaluator = DummyQcEvaluator()
            self.soft_evaluator = DummySoftEvaluator()

    monkeypatch.setattr(cli_module, "Evaluator", DummyEvaluator)

    result = runner.invoke(app, ["measure", "."])

    assert result.exit_code == 0
    assert "FINAL VERDICT" not in result.stdout


def test_refine_delegates_to_engine(monkeypatch: Any, tmp_path: Path) -> None:
    """
    Test that refine delegates to the engine with loop-oriented options.
    """
    captured: dict[str, object] = {}

    def fake_run_refine(**kwargs: object) -> dict[str, object]:
        captured.update(kwargs)
        return {
            "rounds_completed": 1,
            "winner_id": "l1-1",
            "stop_reason": "single round completed",
        }

    monkeypatch.setattr(cli_module, "run_refine", fake_run_refine)

    result = runner.invoke(
        app,
        [
            "refine",
            str(tmp_path),
            "--max-retries",
            "2",
            "--loop",
            "--max-rounds",
            "4",
        ],
    )

    assert result.exit_code == 0
    assert captured["target_path"] == tmp_path
    assert captured["max_retries"] == 2
    assert captured["loop"] is True
    assert captured["max_rounds"] == 4
    assert "winner_id: l1-1" in result.stdout
    assert "rounds_completed: 1" in result.stdout
    assert "stop_reason: single round completed" in result.stdout


def test_refine_defaults_to_single_round(monkeypatch: Any, tmp_path: Path) -> None:
    """
    Test that refine no longer accepts steps and defaults to a single round.
    """
    captured: dict[str, object] = {}

    def fake_run_refine(**kwargs: object) -> dict[str, object]:
        captured.update(kwargs)
        return {
            "rounds_completed": 1,
            "winner_id": "baseline",
            "stop_reason": "single round completed",
        }

    monkeypatch.setattr(cli_module, "run_refine", fake_run_refine)

    result = runner.invoke(app, ["refine", str(tmp_path)])

    assert result.exit_code == 0
    assert captured["target_path"] == tmp_path
    assert captured["max_retries"] == 3
    assert captured["loop"] is False
    assert captured["max_rounds"] == 3


def test_refine_resolves_relative_target_path(monkeypatch: Any) -> None:
    captured: dict[str, object] = {}

    def fake_run_refine(**kwargs: object) -> dict[str, object]:
        captured.update(kwargs)
        return {
            "rounds_completed": 1,
            "winner_id": "baseline",
            "stop_reason": "single round completed",
        }

    monkeypatch.setattr(cli_module, "run_refine", fake_run_refine)

    with runner.isolated_filesystem():
        result = runner.invoke(app, ["refine", "."])
        expected_path = Path.cwd().resolve()

    assert result.exit_code == 0
    assert captured["target_path"] == expected_path


def test_measure_surfaces_hard_tool_errors(monkeypatch: Any) -> None:
    """
    Test that measure prints hard-tool error details when tool invocations fail early.
    """
    class DummyHardEvaluator:
        def evaluate(self) -> dict[str, Any]:
            return {
                "all_passed": False,
                "ruff": {
                    "status": "failed",
                    "issues": [],
                    "error_message": "No module named ruff",
                },
                "mypy": {"status": "failed", "output": "No module named mypy"},
                "ty": {
                    "status": "warning",
                    "error_message": "ty executable not found. Skipping ty checks.",
                },
                "radon_cc": {
                    "status": "warning",
                    "issues": [],
                    "error_message": "No module named radon",
                },
                "radon_mi": {"status": "success", "mi_scores": {}},
                "pytest": {
                    "status": "failed",
                    "error_message": "No module named pytest",
                },
            }

    class DummyQcEvaluator:
        def evaluate(self) -> dict[str, Any]:
            return {"all_passed": True, "failures": []}

    class DummySoftEvaluator:
        def evaluate(self) -> dict[str, Any]:
            return {
                "package_summary": {
                    "total_files": 1,
                    "total_tokens": 1,
                    "package_understanding": "Mock understanding",
                },
                "understandability_score": 100.0,
                "qa_results": {"sampled_entities": []},
            }

        def generate_final_report(
            self,
            hard_results: dict[str, Any],
            qc_results: dict[str, Any],
            soft_results: dict[str, Any],
        ) -> dict[str, Any]:
            return {"verdict": "Fail", "summary": "Mock summary", "suggestions": []}

    class DummyEvaluator:
        def __init__(self, path: str):
            self.path = path
            self.hard_evaluator = DummyHardEvaluator()
            self.qc_evaluator = DummyQcEvaluator()
            self.soft_evaluator = DummySoftEvaluator()

    monkeypatch.setattr(cli_module, "Evaluator", DummyEvaluator)

    result = runner.invoke(app, ["measure", "."])

    assert result.exit_code == 1
    assert "Ruff issues found" in result.stdout
    assert "No module named ruff" in result.stdout
    assert "Mypy issues found" in result.stdout
    assert "No module named mypy" in result.stdout
    assert "Pytest/Coverage issues found" in result.stdout
    assert "No module named pytest" in result.stdout


def test_mi_scorecard_uses_warning_color_below_70() -> None:
    """
    Test that MI below 70 is no longer rendered as healthy green.
    """
    assert cli_module._mi_scorecard_color(65.0) == "yellow"


def test_mi_scorecard_uses_green_at_70() -> None:
    """
    Test that MI 70 is rendered at the healthy threshold.
    """
    assert cli_module._mi_scorecard_color(70.0) == "green"
