from typing import Any

from python_harness.refine_feedback_extractors import (
    generic_summary,
    parser_for,
    tool_name,
)
from python_harness.refine_feedback_utils import feedback_payload


def parse_failure_feedback(feedback: str) -> dict[str, Any]:
    tool = tool_name(feedback)
    parser = parser_for(tool)
    diagnostics = parser(feedback)
    if not diagnostics:
        diagnostics = generic_summary(feedback)
    return feedback_payload(tool=tool, diagnostics=diagnostics)


def extract_failed_files(feedback: str) -> list[str]:
    parsed = parse_failure_feedback(feedback)
    return [str(file_path) for file_path in parsed["failed_files"]]


def dominant_failure_signature(feedback: str) -> str:
    parsed = parse_failure_feedback(feedback)
    signatures = parsed["signatures"]
    if isinstance(signatures, list) and signatures:
        return str(signatures[0])
    return str(parsed["summary"])
