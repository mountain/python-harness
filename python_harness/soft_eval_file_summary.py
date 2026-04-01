"""
Helpers for file-level soft evaluation summaries.
"""

import hashlib
from pathlib import Path
from typing import Any

from pydantic import BaseModel

_FILE_SUMMARY_CACHE: dict[tuple[str, str], dict[str, Any]] = {}


class FileSummary(BaseModel):
    summary: str
    key_entities: list[str]
    complexity_score: int


def clear_file_summary_cache() -> None:
    _FILE_SUMMARY_CACHE.clear()


def build_relative_file_path(file_path: Path, target_path: Path) -> str:
    try:
        return str(file_path.relative_to(target_path))
    except ValueError:
        return str(file_path)


def build_default_file_summary(
    file_path: Path,
    target_path: Path,
    tokens: int,
) -> dict[str, Any]:
    return {
        "file": build_relative_file_path(file_path, target_path),
        "tokens": tokens,
        "summary": f"File {file_path.name} contains {tokens} tokens.",
        "key_entities": [],
    }


def should_call_file_summary_llm(client: Any, content: str, tokens: int) -> bool:
    return bool(client and content and 0 < tokens < 100000)


def build_file_summary_messages(
    file_path: Path,
    content: str,
) -> list[dict[str, str]]:
    sys_prompt = (
        "You are a senior Python architect. Analyze the provided Python "
        "file and provide a concise summary of its purpose, a list of "
        "its key entities (classes/functions/globals), and an estimated "
        "cognitive complexity score (1-10).\n"
        "Output MUST be in valid JSON matching this schema: "
        '{"summary": "str", "key_entities": ["str"], "complexity_score": 1}'
    )
    return [
        {"role": "system", "content": sys_prompt},
        {
            "role": "user",
            "content": (
                f"File name: {file_path.name}\n\nContent:\n"
                f"```python\n{content}\n```"
            ),
        },
    ]


def parse_file_summary_response(
    raw_content: str,
    fallback_summary: dict[str, Any],
) -> dict[str, Any]:
    parsed = FileSummary.model_validate_json(raw_content)
    return {
        "file": fallback_summary["file"],
        "tokens": fallback_summary["tokens"],
        "summary": parsed.summary,
        "key_entities": parsed.key_entities,
    }


def build_file_summary_cache_key(model_name: str, content: str) -> tuple[str, str]:
    digest = hashlib.sha256(content.encode("utf-8")).hexdigest()
    return (model_name, digest)


def get_cached_file_summary(
    cache_key: tuple[str, str],
    fallback_summary: dict[str, Any],
) -> dict[str, Any] | None:
    cached_summary = _FILE_SUMMARY_CACHE.get(cache_key)
    if cached_summary is None:
        return None
    return {
        "file": fallback_summary["file"],
        "tokens": fallback_summary["tokens"],
        "summary": cached_summary["summary"],
        "key_entities": cached_summary["key_entities"],
    }


def cache_file_summary(
    cache_key: tuple[str, str],
    summary: dict[str, Any],
) -> None:
    _FILE_SUMMARY_CACHE[cache_key] = {
        "summary": summary["summary"],
        "key_entities": summary["key_entities"],
    }
