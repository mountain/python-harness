"""
Tests for CLI functionality.
"""

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


def test_refine_exits_when_no_suggestions(monkeypatch: Any) -> None:
    """
    Test that refine exits early when baseline report has no suggestions.
    """
    class DummyHardEvaluator:
        def evaluate(self) -> dict[str, Any]:
            return {"all_passed": True}

    class DummySoftEvaluator:
        def evaluate(self) -> dict[str, Any]:
            return {"status": "success"}

        def generate_final_report(
            self,
            hard_results: dict[str, Any],
            qc_results: dict[str, Any],
            soft_results: dict[str, Any],
        ) -> dict[str, Any]:
            return {"suggestions": []}

    class DummyEvaluator:
        def __init__(self, path: str):
            self.path = path
            self.hard_evaluator = DummyHardEvaluator()
            self.soft_evaluator = DummySoftEvaluator()

    monkeypatch.setattr(cli_module, "Evaluator", DummyEvaluator)

    result = runner.invoke(app, ["refine", "."])

    assert result.exit_code == 0
    assert "No suggestions found to evolve. Exiting." in result.stdout


def test_refine_reports_suggestions(monkeypatch: Any) -> None:
    """
    Test that refine reports suggestion count when baseline suggestions exist.
    """
    class DummyHardEvaluator:
        def evaluate(self) -> dict[str, Any]:
            return {"all_passed": True}

    class DummySoftEvaluator:
        def evaluate(self) -> dict[str, Any]:
            return {"status": "success"}

        def generate_final_report(
            self,
            hard_results: dict[str, Any],
            qc_results: dict[str, Any],
            soft_results: dict[str, Any],
        ) -> dict[str, Any]:
            return {"suggestions": [{"title": "one"}, {"title": "two"}]}

    class DummyEvaluator:
        def __init__(self, path: str):
            self.path = path
            self.hard_evaluator = DummyHardEvaluator()
            self.soft_evaluator = DummySoftEvaluator()

    monkeypatch.setattr(cli_module, "Evaluator", DummyEvaluator)

    result = runner.invoke(app, ["refine", "."])

    assert result.exit_code == 0
    assert "Found 2 suggestions. Starting evolution branches..." in result.stdout
    assert "Evolution engine skeleton ready." in result.stdout
