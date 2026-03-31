import shutil
from pathlib import Path


def create_candidate_workspace(parent: Path, root: Path, candidate_id: str) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    workspace = root / candidate_id
    if workspace.exists():
        shutil.rmtree(workspace)
    shutil.copytree(parent, workspace)
    return workspace


def adopt_candidate_workspace(source: Path, target: Path) -> None:
    for child in list(target.iterdir()):
        if child.name == ".git":
            continue
        if child.is_dir():
            shutil.rmtree(child)
        else:
            child.unlink()

    for child in source.iterdir():
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
