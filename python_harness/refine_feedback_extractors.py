import re
from typing import Any

from python_harness.refine_feedback_patterns import (
    MYPY_LINE_PATTERN,
    PYTEST_FAILED_PATTERN,
    RUFF_HEADER_PATTERN,
    RUFF_LOCATION_PATTERN,
)

Diagnostic = dict[str, Any]

_MAX_DIAGNOSTICS = 5


def _has_matching_line(feedback: str, pattern: re.Pattern[str]) -> bool:
    return any(pattern.match(line.strip()) for line in feedback.splitlines())


def tool_name(feedback: str) -> str:
    if _has_matching_line(feedback, MYPY_LINE_PATTERN):
        return "mypy"
    if _has_matching_line(feedback, RUFF_LOCATION_PATTERN):
        return "ruff"
    if _has_matching_line(
        feedback,
        PYTEST_FAILED_PATTERN,
    ) or "AssertionError" in feedback:
        return "pytest"
    return "unknown"


def _parse_mypy(feedback: str) -> list[Diagnostic]:
    diagnostics: list[Diagnostic] = []
    for line in feedback.splitlines():
        match = MYPY_LINE_PATTERN.match(line.strip())
        if match is None:
            continue
        diagnostics.append(
            {
                "file": match.group("file"),
                "line": int(match.group("line")),
                "code": match.group("kind"),
                "message": match.group("message").strip(),
            }
        )
    return diagnostics[:_MAX_DIAGNOSTICS]


def _parse_ruff(feedback: str) -> list[Diagnostic]:
    diagnostics: list[Diagnostic] = []
    current_header: tuple[str, str] | None = None
    for raw_line in feedback.splitlines():
        header = RUFF_HEADER_PATTERN.match(raw_line.strip())
        if header is not None:
            current_header = (
                header.group("code"),
                header.group("message").strip() or header.group("code"),
            )
            continue
        location = RUFF_LOCATION_PATTERN.match(raw_line.strip())
        if location is None or current_header is None:
            continue
        diagnostics.append(
            {
                "file": location.group("file"),
                "line": int(location.group("line")),
                "code": current_header[0],
                "message": current_header[1],
            }
        )
        current_header = None
    return diagnostics[:_MAX_DIAGNOSTICS]


def _parse_pytest(feedback: str) -> list[Diagnostic]:
    diagnostics: list[Diagnostic] = []
    for line in feedback.splitlines():
        match = PYTEST_FAILED_PATTERN.match(line.strip())
        if match is None:
            continue
        diagnostics.append(
            {
                "file": match.group("file"),
                "line": 0,
                "code": "failed",
                "message": match.group("message").strip(),
            }
        )
    return diagnostics[:_MAX_DIAGNOSTICS]


def generic_summary(feedback: str) -> list[Diagnostic]:
    for line in feedback.splitlines():
        stripped = line.strip()
        if stripped:
            return [{"file": "", "line": 0, "code": "unknown", "message": stripped}]
    return []


def parser_for(tool: str) -> Any:
    parsers = {
        "mypy": _parse_mypy,
        "ruff": _parse_ruff,
        "pytest": _parse_pytest,
        "unknown": generic_summary,
    }
    return parsers[tool]
