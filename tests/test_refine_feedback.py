from python_harness.refine_feedback import (
    dominant_failure_signature,
    extract_failed_files,
    format_failure_feedback,
    parse_failure_feedback,
)


def test_parse_failure_feedback_extracts_mypy_diagnostics() -> None:
    feedback = (
        'python_harness/cli.py:107: error: Returning Any from function declared '
        'to return "str"\n'
        "python_harness/cli.py:121: note: Revealed type is \"builtins.str\"\n"
    )

    parsed = parse_failure_feedback(feedback)

    assert parsed["tool"] == "mypy"
    assert parsed["failed_files"] == ["python_harness/cli.py"]
    assert parsed["diagnostics"][0]["line"] == 107
    assert parsed["diagnostics"][0]["code"] == "error"
    assert "Returning Any" in parsed["summary"]


def test_format_failure_feedback_lists_ruff_files_and_retry_guidance() -> None:
    feedback = (
        "F401 unused import 'json'\n"
        " --> python_harness/refine_rounds.py:4:8\n"
        "\n"
        "E501 line too long (95 > 88)\n"
        " --> python_harness/refine_rounds.py:40:89\n"
    )

    formatted = format_failure_feedback(feedback)

    assert "Tool: ruff" in formatted
    assert "- python_harness/refine_rounds.py" in formatted
    assert "Do not rewrite comments, docstrings, or unrelated imports." in formatted


def test_extract_failed_files_and_signature_fall_back_for_unknown_feedback() -> None:
    feedback = "Something unexpected happened"

    assert extract_failed_files(feedback) == []
    assert (
        dominant_failure_signature(feedback)
        == "unknown:Something unexpected happened"
    )
