"""
Helpers for Radon target discovery and output parsing.
"""

import json
from pathlib import Path
from typing import Any

from python_harness.python_file_inventory import collect_python_files

RADON_COMPLEXITY_THRESHOLD = 15
RADON_MISSING_MESSAGE = "radon executable not found. Please install it."


def collect_radon_metric_targets(target_path: Path) -> list[str]:
    """
    Collect non-test Python files used by Radon metrics.
    """
    return [str(file_path) for file_path in collect_python_files(target_path)]


def parse_radon_cc_issues(data: dict[str, Any]) -> list[dict[str, Any]]:
    """
    Extract only blocks above the configured complexity threshold.
    """
    issues: list[dict[str, Any]] = []
    for file_path, blocks in data.items():
        if not isinstance(blocks, list):
            continue
        for block in blocks:
            if not isinstance(block, dict):
                continue
            if block.get("complexity", 0) > RADON_COMPLEXITY_THRESHOLD:
                issues.append(
                    {
                        "file": file_path,
                        "name": block.get("name"),
                        "type": block.get("type"),
                        "complexity": block.get("complexity"),
                    }
                )
    return issues


def parse_radon_mi_scores(data: dict[str, Any]) -> dict[str, float]:
    """
    Extract maintainability scores with compatibility defaults.
    """
    return {
        file_path: float(info.get("mi", 100.0))
        for file_path, info in data.items()
        if isinstance(info, dict)
    }


def load_radon_json(stdout: str) -> dict[str, Any]:
    """
    Parse Radon JSON output with an empty-dict fallback.
    """
    if not stdout:
        return {}
    payload = json.loads(stdout)
    return payload if isinstance(payload, dict) else {}


def radon_missing_result(*, include_scores: bool = False) -> dict[str, Any]:
    """
    Build the warning payload used when Radon is unavailable.
    """
    result: dict[str, Any] = {
        "status": "warning",
        "error_message": RADON_MISSING_MESSAGE,
    }
    if include_scores:
        result["mi_scores"] = {}
    else:
        result["issues"] = []
    return result
