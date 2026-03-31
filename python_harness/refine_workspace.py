import shutil
import tempfile
from collections.abc import Callable, Iterable
from pathlib import Path


def _copytree_ignore(
    parent: Path,
    root: Path,
) -> Callable[[str, list[str]], Iterable[str]] | None:
    if root.parent == parent:
        return shutil.ignore_patterns(root.name)
    return None


def create_candidate_workspace(parent: Path, root: Path, candidate_id: str) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    workspace = root / candidate_id
    if workspace.exists():
        shutil.rmtree(workspace)
    shutil.copytree(parent, workspace, ignore=_copytree_ignore(parent, root))
    return workspace


def _safe_source(source: Path, target: Path) -> Path:
    if not source.is_relative_to(target):
        return source

    temp_root = Path(tempfile.mkdtemp(prefix="harness-adopt-"))
    temp_source = temp_root / source.name
    shutil.copytree(source, temp_source, ignore=shutil.ignore_patterns(".git"))
    return temp_source


def adopt_candidate_workspace(source: Path, target: Path) -> None:
    safe_source = _safe_source(source, target)
    for child in list(target.iterdir()):
        if child.name == ".git":
            continue
        if child.is_dir():
            shutil.rmtree(child)
        else:
            child.unlink()

    for child in safe_source.iterdir():
        if child.name == ".git":
            continue
        destination = target / child.name
        if child.is_dir():
            shutil.copytree(child, destination)
        else:
            shutil.copy2(child, destination)


def cleanup_workspace(path: Path) -> None:
    if path.exists():
        shutil.rmtree(path)
