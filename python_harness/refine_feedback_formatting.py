from python_harness.refine_feedback_parsing import parse_failure_feedback


def format_failure_feedback(feedback: str) -> str:
    parsed = parse_failure_feedback(feedback)
    lines = [
        "Structured guardrail failure summary:",
        f"Tool: {parsed['tool']}",
        "Failing files:",
    ]
    failed_files = parsed["failed_files"]
    if isinstance(failed_files, list) and failed_files:
        lines.extend(f"- {file_path}" for file_path in failed_files)
    else:
        lines.append("- none identified")
    lines.append("Key diagnostics:")
    diagnostics = parsed["diagnostics"]
    if not isinstance(diagnostics, list):
        diagnostics = []
    for diagnostic in diagnostics:
        location = str(diagnostic.get("file") or "unknown")
        if diagnostic.get("line"):
            location = f"{location}:{diagnostic['line']}"
        code = str(diagnostic.get("code") or "unknown")
        message = str(diagnostic.get("message") or "").strip()
        lines.append(f"- {location} | {code} | {message}")
    lines.extend(
        [
            "Retry instructions:",
            "- Fix only the diagnostics above.",
            "- Keep changes local to the failing file(s).",
            "- Do not rewrite comments, docstrings, or unrelated imports.",
        ]
    )
    return "\n".join(lines)
