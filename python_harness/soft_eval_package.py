"""
Helpers for package-level soft evaluation summaries.
"""

from typing import Any


def build_package_understanding(total_files: int, total_tokens: int) -> str:
    return (
        f"The package contains {total_files} files with a total cognitive load "
        f"of {total_tokens} tokens."
    )


def build_package_manifest(file_summaries: list[dict[str, Any]]) -> str:
    manifest_lines = [
        f"- {summary['file']}: {summary['summary']} "
        f"(Entities: {', '.join(summary['key_entities'])})"
        for summary in file_summaries
    ]
    return "\n".join(manifest_lines)


def build_package_synthesis_messages(manifest: str) -> list[dict[str, str]]:
    sys_prompt = (
        "You are a senior software architect. Based on the following "
        "summaries of individual files in a Python package, write a "
        "coherent, high-level explanation of how this entire package "
        "works and what its primary responsibilities are. Be concise "
        "but comprehensive."
    )
    return [
        {"role": "system", "content": sys_prompt},
        {"role": "user", "content": f"Package files and summaries:\n{manifest}"},
    ]
