"""
Python file discovery helpers.
"""

from pathlib import Path

SKIPPED_DIRS = {"__pycache__", "env", "test", "tests", "vendors", "venv"}


def should_skip_python_path(file_path: Path, root: Path) -> bool:
    if file_path.name.startswith("test_") or file_path.name.endswith("_test.py"):
        return True
    try:
        relative_parts = file_path.relative_to(root).parts
    except ValueError:
        relative_parts = file_path.parts
    return any(part.startswith(".") or part in SKIPPED_DIRS for part in relative_parts)


def collect_python_files(root: Path) -> list[Path]:
    if root.is_file():
        return [root] if root.suffix == ".py" else []
    return [
        file_path
        for file_path in sorted(root.rglob("*.py"))
        if not should_skip_python_path(file_path, root)
    ]
