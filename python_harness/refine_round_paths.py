from pathlib import Path


def default_workspace_root(target_path: Path) -> Path:
    return target_path / ".harness-refine"


def validate_workspace_root(target_path: Path, workspace_root: Path) -> None:
    if workspace_root == target_path:
        raise ValueError("workspace_root must not be target_path itself")
    if (
        workspace_root.is_relative_to(target_path)
        and workspace_root.parent != target_path
    ):
        raise ValueError("workspace_root inside target_path must be a direct child")
