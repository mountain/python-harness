from python_harness.refine_execution_support import (
    advance_stagnation,
    build_guardrail_failure_result,
)


def test_build_guardrail_failure_result_captures_autofix_feedback() -> None:
    result = build_guardrail_failure_result(
        pre_autofix_feedback=(
            "python_harness/cli.py:10: error: Name 'x' is not defined"
        ),
        autofix_ok=True,
        autofix_output="ruff fixed imports",
        post_autofix_feedback=(
            "python_harness/cli.py:12: error: Returning Any from function "
            'declared to return "str"'
        ),
    )

    assert result.feedback_for_retry.startswith(
        "Structured guardrail failure summary:"
    )
    assert "Returning Any from function" in result.feedback_for_retry
    assert result.guardrail_entry["pre_autofix"] == {
        "raw": "python_harness/cli.py:10: error: Name 'x' is not defined",
        "summary": "python_harness/cli.py:10 | error | Name 'x' is not defined",
        "failed_files": ["python_harness/cli.py"],
        "signatures": [
            "python_harness/cli.py:10:error:Name 'x' is not defined",
        ],
    }
    assert result.guardrail_entry["autofix"] == {
        "ok": True,
        "output": "ruff fixed imports",
    }
    assert result.guardrail_entry["post_autofix"]["structured_feedback"].startswith(
        "Structured guardrail failure summary:"
    )
    assert result.signature == (
        'python_harness/cli.py:12:error:Returning Any from function declared to '
        'return "str"'
    )


def test_advance_stagnation_increments_on_same_signature_and_resets_on_change() -> None:
    signature, count = advance_stagnation(
        "",
        0,
        'python_harness/cli.py:12:error:Returning Any from function declared to '
        'return "str"',
    )
    assert signature == (
        'python_harness/cli.py:12:error:Returning Any from function declared to '
        'return "str"'
    )
    assert count == 1

    signature, count = advance_stagnation(
        signature,
        count,
        'python_harness/cli.py:12:error:Returning Any from function declared to '
        'return "str"',
    )
    assert signature == (
        'python_harness/cli.py:12:error:Returning Any from function declared to '
        'return "str"'
    )
    assert count == 2

    signature, count = advance_stagnation(
        signature,
        count,
        "python_harness/cli.py:99:error:Incompatible return value type",
    )
    assert signature == "python_harness/cli.py:99:error:Incompatible return value type"
    assert count == 1


def test_build_guardrail_failure_result_handles_missing_file_signatures() -> None:
    result = build_guardrail_failure_result(
        pre_autofix_feedback="pytest failed",
        autofix_ok=False,
        autofix_output="no changes",
        post_autofix_feedback="pytest failed",
    )

    assert result.signature == "unknown:pytest failed"
    assert result.guardrail_entry["pre_autofix"]["failed_files"] == []
    assert result.guardrail_entry["post_autofix"]["failed_files"] == []
    assert result.guardrail_entry["autofix"] == {"ok": False, "output": "no changes"}
