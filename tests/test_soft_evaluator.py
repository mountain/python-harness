"""
Tests for soft evaluation logic.
"""

import os
from pathlib import Path
from typing import Any, cast

from python_harness.soft_evaluator import SoftEvaluator


class _FakeMessage:
    def __init__(self, content: str | None):
        self.content = content


class _FakeChoice:
    def __init__(self, content: str | None):
        self.message = _FakeMessage(content)


class _FakeCompletion:
    def __init__(self, content: str | None):
        self.choices = [_FakeChoice(content)]


class _FakeCompletions:
    def __init__(self, content: str | None = None, error: Exception | None = None):
        self.content = content
        self.error = error

    def create(self, *args: Any, **kwargs: Any) -> _FakeCompletion:
        if self.error:
            raise self.error
        return _FakeCompletion(self.content)


class _FakeChat:
    def __init__(self, content: str | None = None, error: Exception | None = None):
        self.completions = _FakeCompletions(content, error)


class _FakeClient:
    def __init__(self, content: str | None = None, error: Exception | None = None):
        self.chat = _FakeChat(content, error)


def test_soft_evaluator_methods() -> None:
    """
    Test methods of SoftEvaluator.
    """
    # Create a dummy file to test the token complexity calculation
    dummy_file = Path("dummy_soft.py")
    with open(dummy_file, "w") as f:
        f.write("def foo():\n    pass\n")

    # Create an empty .env file or just temporarily remove LLM_API_KEY from env
    # so we don't accidentally spend tokens during tests unless explicitly intended.
    old_key = os.environ.pop("LLM_API_KEY", None)

    try:
        evaluator = SoftEvaluator(".")
        
        file_summary = evaluator.summarize_file(dummy_file)
        assert "tokens" in file_summary
        assert "summary" in file_summary
        
        pkg_summary = evaluator.summarize_package()
        assert "total_tokens" in pkg_summary
        assert "file_level_summaries" in pkg_summary
        
        eval_result = evaluator.evaluate()
        assert eval_result["status"] == "success"
        assert "understandability_score" in eval_result
    finally:
        if os.path.exists(dummy_file):
            os.remove(dummy_file)
        if old_key is not None:
            os.environ["LLM_API_KEY"] = old_key


def test_generate_final_report_mock_fails_on_hard_failure() -> None:
    """
    Test that mock final reports still fail when hard evaluation fails.
    """
    old_key = os.environ.pop("LLM_API_KEY", None)

    try:
        evaluator = SoftEvaluator(".")
        report = evaluator.generate_final_report(
            {
                "all_passed": False,
                "pytest": {
                    "status": "failed",
                    "error_message": (
                        "Test coverage is 63.00%, "
                        "which is below the 90% threshold."
                    ),
                },
                "radon_cc": {"issues": []},
                "radon_mi": {"mi_scores": {}},
            },
            {"all_passed": True, "failures": []},
            {"understandability_score": 85.0, "qa_results": {"sampled_entities": []}},
        )

        assert report["verdict"] == "Fail (Mock)"
        assert "63.00%" in report["summary"]
    finally:
        if old_key is not None:
            os.environ["LLM_API_KEY"] = old_key


def test_read_file_text_helper_reads_utf8_content(tmp_path: Path) -> None:
    """
    Test that the file-reading helper returns UTF-8 text content.
    """
    file_path = tmp_path / "sample.py"
    file_path.write_text("print('hello')\n", encoding="utf-8")

    evaluator = SoftEvaluator(str(tmp_path))

    assert evaluator._read_file_text(file_path) == "print('hello')\n"


def test_count_tokens_helper_returns_zero_without_encoding(tmp_path: Path) -> None:
    """
    Test that the token helper returns zero when tokenizer is unavailable.
    """
    evaluator = SoftEvaluator(str(tmp_path))
    evaluator.encoding = None

    assert evaluator._count_tokens("print('hello')\n") == 0


def test_get_python_files_filters_hidden_and_virtualenv_dirs(tmp_path: Path) -> None:
    """
    Test that Python file discovery excludes hidden and virtualenv-style directories.
    """
    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg" / "keep.py").write_text("x = 1\n")
    (tmp_path / ".hidden").mkdir()
    (tmp_path / ".hidden" / "skip.py").write_text("x = 1\n")
    (tmp_path / "venv").mkdir()
    (tmp_path / "venv" / "skip.py").write_text("x = 1\n")
    (tmp_path / "vendors").mkdir()
    (tmp_path / "vendors" / "skip.py").write_text("x = 1\n")

    evaluator = SoftEvaluator(str(tmp_path))

    assert evaluator._get_python_files() == [tmp_path / "pkg" / "keep.py"]


def test_calculate_token_complexity_handles_read_error(tmp_path: Path) -> None:
    """
    Test that token complexity falls back to zero when file reading fails.
    """
    evaluator = SoftEvaluator(str(tmp_path))

    assert evaluator.calculate_token_complexity(tmp_path / "missing.py") == 0


def test_extract_ast_entities_collects_functions_classes_and_fan_out(
    tmp_path: Path,
) -> None:
    """
    Test AST extraction for entities and imported-module fan-out.
    """
    evaluator = SoftEvaluator(str(tmp_path))
    content = (
        "import os\n"
        "from pathlib import Path\n\n"
        "def foo():\n"
        "    return 1\n\n"
        "class Bar:\n"
        "    pass\n"
    )

    evaluator._extract_ast_entities(tmp_path / "sample.py", content)

    assert {entity["name"] for entity in evaluator.extracted_entities} == {"foo", "Bar"}
    assert {entity["fan_out"] for entity in evaluator.extracted_entities} == {2}


def test_summarize_file_returns_fallback_without_client(tmp_path: Path) -> None:
    """
    Test summarize_file fallback behavior without an LLM client.
    """
    file_path = tmp_path / "sample.py"
    file_path.write_text("def foo():\n    return 1\n", encoding="utf-8")
    evaluator = SoftEvaluator(str(tmp_path))
    evaluator.client = None

    result = evaluator.summarize_file(file_path)

    assert result["file"] == "sample.py"
    assert result["summary"].startswith("File sample.py contains")
    assert result["key_entities"] == []
    assert any(entity["name"] == "foo" for entity in evaluator.extracted_entities)


def test_summarize_file_uses_llm_response(tmp_path: Path) -> None:
    """
    Test summarize_file when the LLM returns structured JSON.
    """
    file_path = tmp_path / "sample.py"
    file_path.write_text("def foo():\n    return 1\n", encoding="utf-8")
    evaluator = SoftEvaluator(str(tmp_path))
    evaluator.client = cast(
        Any,
        _FakeClient(
            '{"summary":"Custom summary","key_entities":["foo"],"complexity_score":3}'
        ),
    )

    result = evaluator.summarize_file(file_path)

    assert result["summary"] == "Custom summary"
    assert result["key_entities"] == ["foo"]


def test_summarize_package_uses_llm_synthesis(tmp_path: Path) -> None:
    """
    Test summarize_package when package synthesis uses the LLM response.
    """
    (tmp_path / "a.py").write_text("def a():\n    return 1\n", encoding="utf-8")
    evaluator = SoftEvaluator(str(tmp_path))
    evaluator.client = cast(Any, _FakeClient("Package synthesis"))

    result = evaluator.summarize_package()

    assert result["total_files"] == 1
    assert result["package_understanding"] == "Package synthesis"


def test_run_sampling_qa_mock_path_with_sampled_entities(tmp_path: Path) -> None:
    """
    Test sampling QA mock path for extracted entities.
    """
    evaluator = SoftEvaluator(str(tmp_path))
    evaluator.extracted_entities = [
        {
            "file": "a.py",
            "type": "Function",
            "name": "foo",
            "code": "def foo():\n    pass",
        }
    ]

    result = evaluator.run_sampling_qa()

    assert result["qa_score"] == 100.0
    assert result["sampled_entities"][0]["entity"] == "Function foo (from a.py)"


def test_run_sampling_qa_client_success(monkeypatch: Any, tmp_path: Path) -> None:
    """
    Test sampling QA when the LLM returns readable JSON.
    """
    monkeypatch.setattr(
        "random.sample", lambda entities, sample_size: entities[:sample_size]
    )
    evaluator = SoftEvaluator(str(tmp_path))
    evaluator.client = cast(
        Any,
        _FakeClient('{"explanation":"ok","readability_score":88,"feedback":"clear"}'),
    )
    evaluator.extracted_entities = [
        {
            "file": "a.py",
            "type": "Function",
            "name": "foo",
            "code": "def foo():\n    pass",
            "fan_out": 1,
        }
    ]

    result = evaluator.run_sampling_qa()

    assert result["qa_score"] == 88.0
    assert result["sampled_entities"][0]["feedback"] == "clear"


def test_generate_final_report_real_path_success(tmp_path: Path) -> None:
    """
    Test final report generation through the real-client path.
    """
    evaluator = SoftEvaluator(str(tmp_path))
    evaluator.client = cast(
        Any,
        _FakeClient('{"verdict":"Pass","summary":"Healthy","suggestions":[]}'),
    )

    report = evaluator.generate_final_report(
        {
            "all_passed": True,
            "ruff": {"status": "success"},
            "mypy": {"status": "success"},
            "pytest": {"status": "success"},
            "radon_cc": {"issues": []},
            "radon_mi": {"mi_scores": {"a.py": 80.0}},
        },
        {"all_passed": True, "failures": []},
        {"understandability_score": 90.0, "qa_results": {"sampled_entities": []}},
    )

    assert report["verdict"] == "Pass"
    assert report["summary"] == "Healthy"


def test_generate_final_report_real_path_handles_errors(tmp_path: Path) -> None:
    """
    Test final report generation error handling on the real-client path.
    """
    evaluator = SoftEvaluator(str(tmp_path))
    evaluator.client = cast(Any, _FakeClient(error=RuntimeError("boom")))

    report = evaluator.generate_final_report(
        {
            "all_passed": True,
            "ruff": {"status": "success"},
            "mypy": {"status": "success"},
            "pytest": {"status": "success"},
            "radon_cc": {"issues": []},
            "radon_mi": {"mi_scores": {"a.py": 80.0}},
        },
        {"all_passed": True, "failures": []},
        {"understandability_score": 90.0, "qa_results": {"sampled_entities": []}},
    )

    assert report["verdict"] == "Error"
    assert "boom" in report["summary"]


def test_evaluate_combines_package_and_qa(monkeypatch: Any, tmp_path: Path) -> None:
    """
    Test evaluate combines package summary and QA results.
    """
    monkeypatch.setattr(
        SoftEvaluator,
        "summarize_package",
        lambda self: {"total_files": 1, "total_tokens": 10},
    )
    monkeypatch.setattr(
        SoftEvaluator,
        "run_sampling_qa",
        lambda self: {"qa_score": 77.0, "sampled_entities": []},
    )
    evaluator = SoftEvaluator(str(tmp_path))

    result = evaluator.evaluate()

    assert result["status"] == "success"
    assert result["understandability_score"] == 77.0
