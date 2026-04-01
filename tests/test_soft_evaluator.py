"""
Tests for soft evaluation logic.
"""

import os
from pathlib import Path
from typing import Any, cast

from python_harness.soft_evaluator import SoftEvaluator, clear_file_summary_cache


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
        self.calls: list[dict[str, Any]] = []

    def create(self, *args: Any, **kwargs: Any) -> _FakeCompletion:
        self.calls.append(kwargs)
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


def test_soft_evaluator_llm_calls_use_request_timeout(tmp_path: Path) -> None:
    evaluator = SoftEvaluator(str(tmp_path))
    payload = '{"summary":"ok","key_entities":["value"],"complexity_score":1}'
    fake_client = _FakeClient(payload)
    evaluator.client = fake_client
    evaluator._summarize_file_with_llm(
        tmp_path / "module.py",
        "def value() -> int:\n    return 1\n",
        {
            "file": "module.py",
            "tokens": 1,
            "summary": "fallback",
            "key_entities": [],
        },
    )

    calls = fake_client.chat.completions.calls
    assert len(calls) == 1
    assert calls[0]["timeout"] == 60.0


def test_soft_evaluator_reuses_cached_file_summary(tmp_path: Path) -> None:
    clear_file_summary_cache()
    sample = tmp_path / "module.py"
    sample.write_text("def value() -> int:\n    return 1\n")
    payload = '{"summary":"ok","key_entities":["value"],"complexity_score":1}'
    fake_client = _FakeClient(payload)

    evaluator_one = SoftEvaluator(str(tmp_path))
    evaluator_one.client = fake_client
    evaluator_one.summarize_file(sample)

    evaluator_two = SoftEvaluator(str(tmp_path))
    evaluator_two.client = fake_client
    evaluator_two.summarize_file(sample)

    calls = fake_client.chat.completions.calls
    assert len(calls) == 1


def test_run_sampling_qa_emits_detailed_progress(
    monkeypatch: Any,
    tmp_path: Path,
) -> None:
    messages: list[str] = []
    evaluator = SoftEvaluator(str(tmp_path))
    payload = (
        '{"explanation":"ok","readability_score":88,'
        '"feedback":"Readable enough."}'
    )
    evaluator.client = _FakeClient(payload)
    evaluator.extracted_entities = [
        {
            "name": "value",
            "type": "Function",
            "code": "def value() -> int:\n    return 1\n",
            "fan_out": 0,
            "file": "module.py",
        }
    ]
    monkeypatch.setattr("python_harness.soft_evaluator.console.print", messages.append)

    evaluator.run_sampling_qa()

    assert any("Blind QA item 1/1 started" in message for message in messages)
    assert any("Blind QA item 1/1 completed" in message for message in messages)


def test_generate_final_report_emits_progress_messages(
    monkeypatch: Any,
    tmp_path: Path,
) -> None:
    messages: list[str] = []
    evaluator = SoftEvaluator(str(tmp_path))
    evaluator.client = _FakeClient(
        '{"verdict":"Pass","summary":"ok","suggestions":[]}'
    )
    monkeypatch.setattr("python_harness.soft_evaluator.console.print", messages.append)

    report = evaluator.generate_final_report(
        {
            "all_passed": True,
            "radon_cc": {"issues": []},
            "radon_mi": {"mi_scores": {"core.py": 80.0}},
        },
        {"all_passed": True, "failures": []},
        {"understandability_score": 88.0, "qa_results": {"sampled_entities": []}},
    )

    assert report["verdict"] == "Pass"
    assert any("Final report synthesis started" in message for message in messages)
    assert any("Final report synthesis completed" in message for message in messages)
    calls = evaluator.client.chat.completions.calls
    assert len(calls) == 1
    assert calls[0]["model"] == evaluator.mini_model_name


def test_summarize_package_emits_file_level_progress(
    monkeypatch: Any,
    tmp_path: Path,
) -> None:
    messages: list[str] = []
    sample = tmp_path / "module.py"
    sample.write_text("def value() -> int:\n    return 1\n")
    evaluator = SoftEvaluator(str(tmp_path))
    monkeypatch.setattr("python_harness.soft_evaluator.console.print", messages.append)

    evaluator.summarize_package()

    assert any("File summary 1/1 started" in message for message in messages)
    assert any("File summary 1/1 completed" in message for message in messages)


def test_summarize_package_files_helper_collects_summaries_and_tokens(
    monkeypatch: Any,
    tmp_path: Path,
) -> None:
    first = tmp_path / "a.py"
    second = tmp_path / "b.py"
    first.write_text("def a():\n    return 1\n", encoding="utf-8")
    second.write_text("def b():\n    return 2\n", encoding="utf-8")
    evaluator = SoftEvaluator(str(tmp_path))
    monkeypatch.setattr(
        SoftEvaluator,
        "summarize_file",
        lambda self, file_path: {
            "file": file_path.name,
            "tokens": 3 if file_path.name == "a.py" else 5,
            "summary": f"summary for {file_path.name}",
            "key_entities": [],
        },
    )

    file_summaries, total_tokens = evaluator._summarize_package_files([first, second])

    assert [summary["file"] for summary in file_summaries] == ["a.py", "b.py"]
    assert total_tokens == 8


def test_determine_verdict_fails_below_mi_70(tmp_path: Path) -> None:
    """
    Test that MI below 70 no longer qualifies for a passing verdict.
    """
    evaluator = SoftEvaluator(str(tmp_path))

    verdict = evaluator._determine_verdict(
        {
            "hard_failed": False,
            "qc_failed": False,
            "avg_mi": 65.0,
            "qa_score": 90.0,
            "cc_issues": [],
        }
    )

    assert verdict == "Fail"


def test_determine_verdict_passes_at_mi_70(tmp_path: Path) -> None:
    """
    Test that MI of 70 is sufficient for a passing verdict.
    """
    evaluator = SoftEvaluator(str(tmp_path))

    verdict = evaluator._determine_verdict(
        {
            "hard_failed": False,
            "qc_failed": False,
            "avg_mi": 70.0,
            "qa_score": 90.0,
            "cc_issues": [],
        }
    )

    assert verdict == "Pass"


def test_final_report_prompt_mentions_mi_70_threshold(tmp_path: Path) -> None:
    """
    Test that the final report prompt advertises the updated MI threshold.
    """
    evaluator = SoftEvaluator(str(tmp_path))

    messages = evaluator._build_final_report_messages(
        {
            "avg_mi": 70.0,
            "cc_issues": [],
            "qa_score": 90.0,
            "hard_errors": [],
            "qc_errors": [],
            "qa_entities": [],
            "hard_failed": False,
            "qc_failed": False,
        }
    )

    assert "Average Maintainability >= 70" in messages[0]["content"]


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
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_skip.py").write_text("x = 1\n")

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


def test_evaluate_sampled_entity_helper_uses_mock_when_client_missing(
    tmp_path: Path,
) -> None:
    evaluator = SoftEvaluator(str(tmp_path))
    evaluator.client = None

    score, feedback = evaluator._evaluate_sampled_entity(
        {
            "file": "a.py",
            "type": "Function",
            "name": "foo",
            "code": "def foo():\n    pass",
            "fan_out": 1,
        }
    )

    assert score == 100.0
    assert feedback == "Mock evaluation: Code is perfectly readable."


def test_request_final_report_helper_parses_client_response(tmp_path: Path) -> None:
    evaluator = SoftEvaluator(str(tmp_path))
    evaluator.client = cast(
        Any,
        _FakeClient('{"verdict":"Pass","summary":"Healthy","suggestions":[]}'),
    )

    report = evaluator._request_final_report(
        {
            "avg_mi": 80.0,
            "cc_issues": [],
            "qa_score": 90.0,
            "hard_errors": [],
            "qc_errors": [],
            "qa_entities": [],
            "hard_failed": False,
            "qc_failed": False,
        }
    )

    assert report == {"verdict": "Pass", "summary": "Healthy", "suggestions": []}


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
