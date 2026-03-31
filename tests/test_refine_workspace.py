from pathlib import Path

from python_harness.refine_workspace import (
    adopt_candidate_workspace,
    create_candidate_workspace,
)


def test_create_candidate_workspace_copies_parent_tree(tmp_path: Path) -> None:
    parent = tmp_path / "parent"
    parent.mkdir()
    (parent / "sample.py").write_text("print('parent')\n")
    root = tmp_path / "workspaces"

    workspace = create_candidate_workspace(parent, root, "candidate-1")

    assert workspace == root / "candidate-1"
    assert (workspace / "sample.py").read_text() == "print('parent')\n"


def test_create_candidate_workspace_ignores_workspace_root_inside_parent(
    tmp_path: Path,
) -> None:
    parent = tmp_path / "parent"
    parent.mkdir()
    (parent / "sample.py").write_text("print('parent')\n")
    root = parent / ".harness-refine"
    workspace = create_candidate_workspace(parent, root, "candidate-1")

    assert workspace == root / "candidate-1"
    assert (workspace / "sample.py").read_text() == "print('parent')\n"
    assert not (workspace / ".harness-refine").exists()


def test_adopt_candidate_workspace_replaces_target_contents(tmp_path: Path) -> None:
    target = tmp_path / "target"
    target.mkdir()
    (target / "old.py").write_text("old\n")
    winner = tmp_path / "winner"
    winner.mkdir()
    (winner / "new.py").write_text("new\n")

    adopt_candidate_workspace(winner, target)

    assert not (target / "old.py").exists()
    assert (target / "new.py").read_text() == "new\n"


def test_adopt_candidate_workspace_preserves_target_git_directory(
    tmp_path: Path,
) -> None:
    target = tmp_path / "target"
    target.mkdir()
    (target / "tracked.py").write_text("old\n")
    target_git = target / ".git"
    target_git.mkdir()
    (target_git / "HEAD").write_text("ref: refs/heads/main\n")

    winner = tmp_path / "winner"
    winner.mkdir()
    (winner / "tracked.py").write_text("new\n")
    winner_git = winner / ".git"
    winner_git.mkdir()
    (winner_git / "HEAD").write_text("ref: refs/heads/feature\n")

    adopt_candidate_workspace(winner, target)

    assert (target / "tracked.py").read_text() == "new\n"
    assert (target / ".git" / "HEAD").read_text() == "ref: refs/heads/main\n"
