from typing import Any

from python_harness.cli_hard_text import (
    CONTINUE_AFTER_HARD_FAILURE,
    HARD_EVALUATION_FAILED,
    HARD_EVALUATION_PASSED,
    RADON_PARSE_MISSING,
    RUFF_ISSUES_FOUND,
    TY_CAPTURE_MISSING,
)


def _print_detail_block(console: Any, title: str, details: str, color: str) -> None:
    normalized_details = [
        line.rstrip() for line in details.splitlines() if line.strip()
    ]
    console.print(f"[{color}]{title}:[/{color}]")
    for line in normalized_details:
        console.print(f"  {line}")
    console.print()


def _print_ruff_issues(
    console: Any,
    issues: list[dict[str, Any]],
    error_message: str = "",
) -> None:
    console.print(RUFF_ISSUES_FOUND)
    for issue in issues:
        file = issue.get("filename", "unknown")
        line = issue.get("location", {}).get("row", "?")
        msg = issue.get("message", "unknown issue")
        console.print(f"  - {file}:{line} {msg}")
    if not issues and error_message:
        console.print(f"  {error_message}")
    console.print()


def _print_ty_result(console: Any, ty_results: dict[str, Any]) -> None:
    status = ty_results.get("status")
    if status == "warning":
        msg = str(ty_results.get("error_message", "ty not found"))
        _print_detail_block(console, "Ty warning", msg, "yellow")
        return
    if status == "success":
        return
    output = str(ty_results.get("output", ""))
    error_msg = str(ty_results.get("error_message", ""))
    if output:
        _print_detail_block(console, "Ty issues found", output, "red")
    elif error_msg:
        _print_detail_block(console, "Ty error", error_msg, "red")
    else:
        console.print(TY_CAPTURE_MISSING)


def _print_radon_cc_result(console: Any, radon_results: dict[str, Any]) -> None:
    status = radon_results.get("status")
    if status == "warning":
        err_msg = str(radon_results.get("error_message", ""))
        _print_detail_block(console, "Radon CC warning", err_msg, "yellow")
        return
    if status != "failed":
        return
    issues = radon_results.get("issues", [])
    if issues:
        console.print(
            f"[red]Cyclomatic Complexity too high "
            f"({len(issues)} functions > 15):[/red]"
        )
        for issue in issues:
            console.print(
                f"  - {issue['file']}: {issue['type']} '{issue['name']}' "
                f"has CC {issue['complexity']}"
            )
        console.print()
        return
    err_msg = str(radon_results.get("error_message", ""))
    if err_msg:
        _print_detail_block(console, "Radon CC error", err_msg, "red")
        return
    console.print(RADON_PARSE_MISSING)
    console.print()


def print_hard_evaluation_summary(console: Any, hard_results: dict[str, Any]) -> None:
    if hard_results["all_passed"]:
        console.print(HARD_EVALUATION_PASSED)
        return
    console.print(HARD_EVALUATION_FAILED)
    console.print()
    ruff_issues = hard_results.get("ruff", {}).get("issues", [])
    if hard_results.get("ruff", {}).get("status") != "success":
        _print_ruff_issues(
            console,
            ruff_issues,
            str(hard_results.get("ruff", {}).get("error_message", "")),
        )
    if hard_results.get("mypy", {}).get("status") != "success":
        output = str(hard_results.get("mypy", {}).get("output", ""))
        _print_detail_block(console, "Mypy issues found", output, "red")
    _print_ty_result(console, hard_results.get("ty", {}))
    _print_radon_cc_result(console, hard_results.get("radon_cc", {}))
    if hard_results.get("pytest", {}).get("status") == "failed":
        error_msg = str(hard_results.get("pytest", {}).get("error_message", ""))
        _print_detail_block(console, "Pytest/Coverage issues found", error_msg, "red")
    console.print(CONTINUE_AFTER_HARD_FAILURE)
