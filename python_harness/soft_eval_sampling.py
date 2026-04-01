"""
Helpers for AST extraction and sampling QA workflows.
"""

import ast
import json
from pathlib import Path
from typing import Any


def extract_ast_entities(file_path: Path, content: str) -> list[dict[str, Any]]:
    try:
        tree = ast.parse(content)
    except SyntaxError:
        return []

    imported_modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imported_modules.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported_modules.add(node.module.split(".")[0])

    fan_out = len(imported_modules)
    extracted_entities: list[dict[str, Any]] = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            continue
        try:
            source_segment = ast.get_source_segment(content, node)
        except Exception:
            continue
        if not source_segment:
            continue
        entity_type = "Class" if isinstance(node, ast.ClassDef) else "Function"
        extracted_entities.append(
            {
                "file": file_path.name,
                "type": entity_type,
                "name": node.name,
                "code": source_segment,
                "fan_out": fan_out,
            }
        )
    return extracted_entities


def build_sampling_qa_messages(
    entity_code: str,
    fan_out: int,
) -> list[dict[str, str]]:
    sys_prompt = (
        "You are an expert Code Reviewer and Software Architect. "
        "You will be given a snippet of Python code (a class or "
        "function) along with its module's Fan-out metric (number "
        "of external dependencies). Your task is to evaluate its "
        "readability and structural cohesion.\n"
        "Output MUST be in valid JSON matching this schema: "
        '{"explanation": "str", "readability_score": 1, '
        '"feedback": "str"}\n'
        "- `explanation`: Briefly explain what this code does.\n"
        "- `readability_score`: A score from 0 to 100.\n"
        "- `feedback`: What makes it easy/hard to understand? "
        "Does a high Fan-out indicate bad cohesion here?"
    )
    user_content = (
        f"Module Fan-out (Dependencies): {fan_out}\n\n"
        f"Code Snippet:\n```python\n{entity_code}\n```"
    )
    return [
        {"role": "system", "content": sys_prompt},
        {"role": "user", "content": user_content},
    ]


def parse_sampling_qa_response(raw_content: str) -> dict[str, Any]:
    result = json.loads(raw_content)
    return {
        "score": float(result.get("readability_score", 100)),
        "feedback": result.get("feedback", ""),
    }


def build_sampled_entity_result(
    entity: dict[str, Any],
    score: float,
    feedback: str,
) -> dict[str, Any]:
    return {
        "entity": f"{entity['type']} {entity['name']} (from {entity['file']})",
        "score": score,
        "feedback": feedback,
    }
