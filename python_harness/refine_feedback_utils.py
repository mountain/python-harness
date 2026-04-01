from typing import Any

from python_harness.refine_feedback_extractors import Diagnostic


def diagnostic_signature(diagnostic: Diagnostic) -> str:
    parts = [
        str(diagnostic.get("file", "")),
        str(diagnostic.get("line", 0)),
        str(diagnostic.get("code", "")),
        str(diagnostic.get("message", "")),
    ]
    return ":".join(part for part in parts if part not in {"", "0"})


def diagnostic_summary_line(diagnostic: Diagnostic) -> str:
    location = str(diagnostic.get("file") or "")
    if diagnostic.get("line"):
        location = f"{location}:{diagnostic['line']}"
    detail = str(diagnostic.get("message") or "").strip()
    code = str(diagnostic.get("code") or "").strip()
    parts = [part for part in [location, code, detail] if part]
    return " | ".join(parts)


def failed_files(diagnostics: list[Diagnostic]) -> list[str]:
    files = [
        str(diagnostic["file"])
        for diagnostic in diagnostics
        if isinstance(diagnostic.get("file"), str) and diagnostic["file"]
    ]
    return list(dict.fromkeys(files))


def feedback_payload(
    *,
    tool: str,
    diagnostics: list[Diagnostic],
) -> dict[str, Any]:
    failing_files = failed_files(diagnostics)
    signatures = [diagnostic_signature(diagnostic) for diagnostic in diagnostics]
    summary_lines = [
        line
        for line in (diagnostic_summary_line(diagnostic) for diagnostic in diagnostics)
        if line
    ]
    summary = " ; ".join(summary_lines[:3]) or "Unknown guardrail failure"
    return {
        "tool": tool,
        "diagnostics": diagnostics,
        "failed_files": failing_files,
        "signatures": signatures or [summary],
        "summary": summary,
    }
