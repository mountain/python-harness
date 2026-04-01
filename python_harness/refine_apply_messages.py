from pathlib import Path

from python_harness.python_file_inventory import collect_python_files
from python_harness.refine_apply_prompt_text import APPLY_SYSTEM_PROMPT
from python_harness.refine_feedback import extract_failed_files


def select_editable_files(
    workspace: Path,
    suggestion: dict[str, str],
    failure_feedback: str,
) -> list[Path]:
    target_file = suggestion.get("target_file", "").strip()
    selected: list[Path] = []
    workspace_root = workspace.resolve()

    def add_file(path: Path) -> bool:
        resolved = path.resolve()
        if not resolved.is_file():
            return False
        if not resolved.is_relative_to(workspace_root):
            return False
        if resolved in selected:
            return False
        selected.append(resolved)
        return len(selected) == 3

    if target_file and target_file != "all":
        target_path = workspace / target_file
        if target_path.is_file():
            add_file(target_path)
        elif target_path.is_dir():
            for file_path in sorted(target_path.rglob("*.py")):
                if add_file(file_path):
                    return selected

    for failed_file in extract_failed_files(failure_feedback):
        if add_file(workspace / failed_file):
            return selected

    if selected:
        return selected

    for file_path in collect_python_files(workspace):
        if add_file(file_path):
            return selected
    return selected


def build_messages(
    workspace: Path,
    suggestion: dict[str, str],
    failure_feedback: str,
    files: list[Path],
) -> list[dict[str, str]]:
    inventory = "\n".join(
        f"- {file_path.relative_to(workspace)}"
        for file_path in collect_python_files(workspace)
    )
    file_blocks = "\n\n".join(
        (
            f"FILE: {file_path.relative_to(workspace)}\n"
            f"```python\n{file_path.read_text(encoding='utf-8')}\n```"
        )
        for file_path in files
    )
    user_prompt = (
        f"Suggestion title: {suggestion.get('title', '')}\n"
        f"Suggestion description: {suggestion.get('description', '')}\n"
        f"Suggestion target_file: {suggestion.get('target_file', 'all')}\n"
        f"Retry feedback: {failure_feedback or 'None'}\n\n"
        f"Workspace python inventory:\n{inventory}\n\n"
        f"Editable file contents:\n{file_blocks}"
    )
    return [
        {"role": "system", "content": APPLY_SYSTEM_PROMPT},
        {"role": "user", "content": user_prompt},
    ]
