# Harness Refine Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a real `harness refine` engine that expands 3 first-layer candidates, re-measures them into 9 second-layer candidates, compares all levels, selects a winner, and optionally repeats with `--loop`.

**Architecture:** Keep `cli.py` thin and move refine behavior into focused modules for models, scoring, workspace management, suggestion application, and orchestration. Drive the implementation with tests first so the fixed `3 + 9` search semantics, retry policy, and loop stopping rules stay deterministic and easy to verify.

**Tech Stack:** Python 3.10, Typer, Rich, pytest, mypy, Ruff, existing `Evaluator` / `soft_eval_report` helpers

---

## File Map

- Create: `python_harness/refine_models.py`
- Create: `python_harness/refine_scoring.py`
- Create: `python_harness/refine_workspace.py`
- Create: `python_harness/refine_apply.py`
- Create: `python_harness/refine_engine.py`
- Modify: `python_harness/cli.py`
- Create: `tests/test_refine_scoring.py`
- Create: `tests/test_refine_workspace.py`
- Create: `tests/test_refine_engine.py`
- Modify: `tests/test_cli.py`

## Shared API Decisions

Use these names consistently across all tasks:

```python
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol


@dataclass(slots=True)
class Candidate:
    id: str
    parent_id: str | None
    depth: int
    workspace: Path
    suggestion_trace: tuple[str, ...]
    evaluation: dict[str, Any] | None = None
    status: str = "pending"
    retry_count: int = 0
    selection_reason: str = ""


@dataclass(slots=True)
class SelectionResult:
    winner: Candidate
    ordered_ids: list[str]
    reason: str


@dataclass(slots=True)
class RefineRoundResult:
    baseline: Candidate
    candidates: list[Candidate] = field(default_factory=list)
    winner: Candidate | None = None
    stop_reason: str = ""


class SuggestionApplier(Protocol):
    def apply(
        self,
        workspace: Path,
        suggestion: dict[str, str],
        failure_feedback: str = "",
    ) -> dict[str, Any]: ...
```

Keep `suggestion_trace` as titles only. The engine can still pass the full suggestion dict into the applier, but titles are enough for ranking summaries and tests.

### Task 1: Lock Candidate Models And Ranking Contracts

**Files:**
- Create: `tests/test_refine_scoring.py`
- Create: `python_harness/refine_models.py`
- Create: `python_harness/refine_scoring.py`

- [ ] **Step 1: Write the failing scoring tests**

```python
from pathlib import Path

from python_harness.refine_models import Candidate
from python_harness.refine_scoring import build_candidate_rank, select_best_candidate


def make_candidate(
    candidate_id: str,
    *,
    verdict: str,
    hard_passed: bool,
    qc_passed: bool,
    avg_mi: float,
    qa_score: float,
    cc_issues: int,
) -> Candidate:
    return Candidate(
        id=candidate_id,
        parent_id=None,
        depth=0,
        workspace=Path("/tmp") / candidate_id,
        suggestion_trace=(),
        evaluation={
            "hard_evaluation": {"all_passed": hard_passed},
            "qc_evaluation": {"all_passed": qc_passed, "failures": []},
            "soft_evaluation": {"understandability_score": qa_score},
            "final_report": {"verdict": verdict},
            "metrics": {
                "avg_mi": avg_mi,
                "qa_score": qa_score,
                "cc_issue_count": cc_issues,
                "hard_failed": not hard_passed,
                "qc_failed": not qc_passed,
            },
        },
    )


def test_build_candidate_rank_prioritizes_passing_hard_and_qc() -> None:
    failed = make_candidate(
        "failed",
        verdict="Fail",
        hard_passed=False,
        qc_passed=True,
        avg_mi=95.0,
        qa_score=95.0,
        cc_issues=0,
    )
    passed = make_candidate(
        "passed",
        verdict="Fail",
        hard_passed=True,
        qc_passed=True,
        avg_mi=60.0,
        qa_score=60.0,
        cc_issues=1,
    )
    assert build_candidate_rank(passed) > build_candidate_rank(failed)


def test_select_best_candidate_compares_all_metrics_deterministically() -> None:
    low = make_candidate(
        "low",
        verdict="Pass",
        hard_passed=True,
        qc_passed=True,
        avg_mi=71.0,
        qa_score=76.0,
        cc_issues=1,
    )
    high = make_candidate(
        "high",
        verdict="Pass",
        hard_passed=True,
        qc_passed=True,
        avg_mi=85.0,
        qa_score=90.0,
        cc_issues=0,
    )
    result = select_best_candidate([low, high])
    assert result.winner.id == "high"
    assert result.ordered_ids == ["high", "low"]
```

- [ ] **Step 2: Run the scoring tests to verify they fail**

Run: `pytest tests/test_refine_scoring.py -q`  
Expected: FAIL with `ModuleNotFoundError` or missing `build_candidate_rank`

- [ ] **Step 3: Write the model module**

```python
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass(slots=True)
class Candidate:
    id: str
    parent_id: str | None
    depth: int
    workspace: Path
    suggestion_trace: tuple[str, ...]
    evaluation: dict[str, Any] | None = None
    status: str = "pending"
    retry_count: int = 0
    selection_reason: str = ""


@dataclass(slots=True)
class SelectionResult:
    winner: Candidate
    ordered_ids: list[str]
    reason: str


@dataclass(slots=True)
class RefineRoundResult:
    baseline: Candidate
    candidates: list[Candidate] = field(default_factory=list)
    winner: Candidate | None = None
    stop_reason: str = ""
```

- [ ] **Step 4: Write the minimal scoring module**

```python
from typing import Any

from python_harness.refine_models import Candidate, SelectionResult
from python_harness.soft_eval_report import extract_metrics


def candidate_metrics(candidate: Candidate) -> dict[str, Any]:
    evaluation = candidate.evaluation or {}
    if "metrics" in evaluation:
        return dict(evaluation["metrics"])
    hard = evaluation.get("hard_evaluation", {})
    qc = evaluation.get("qc_evaluation", {})
    soft = evaluation.get("soft_evaluation", {})
    metrics = extract_metrics(hard, qc, soft)
    return {
        "avg_mi": float(metrics["avg_mi"]),
        "qa_score": float(metrics["qa_score"]),
        "cc_issue_count": len(metrics["cc_issues"]),
        "hard_failed": bool(metrics["hard_failed"]),
        "qc_failed": bool(metrics["qc_failed"]),
    }


def build_candidate_rank(candidate: Candidate) -> tuple[int, int, float, float, int]:
    metrics = candidate_metrics(candidate)
    verdict = str(
        (candidate.evaluation or {}).get("final_report", {}).get("verdict", "Fail")
    )
    passes_hard_qc = int(not metrics["hard_failed"] and not metrics["qc_failed"])
    verdict_is_pass = int(verdict == "Pass")
    return (
        passes_hard_qc,
        verdict_is_pass,
        float(metrics["avg_mi"]),
        float(metrics["qa_score"]),
        -int(metrics["cc_issue_count"]),
    )


def select_best_candidate(candidates: list[Candidate]) -> SelectionResult:
    ordered = sorted(candidates, key=build_candidate_rank, reverse=True)
    winner = ordered[0]
    return SelectionResult(
        winner=winner,
        ordered_ids=[candidate.id for candidate in ordered],
        reason=f"selected by rank {build_candidate_rank(winner)}",
    )
```

- [ ] **Step 5: Run the scoring tests to verify they pass**

Run: `pytest tests/test_refine_scoring.py -q`  
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add tests/test_refine_scoring.py python_harness/refine_models.py python_harness/refine_scoring.py
git commit -m "feat: add refine candidate models and scoring"
```

### Task 2: Add Workspace Isolation Utilities

**Files:**
- Create: `tests/test_refine_workspace.py`
- Create: `python_harness/refine_workspace.py`

- [ ] **Step 1: Write the failing workspace tests**

```python
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
```

- [ ] **Step 2: Run the workspace tests to verify they fail**

Run: `pytest tests/test_refine_workspace.py -q`  
Expected: FAIL with `ModuleNotFoundError` or missing workspace functions

- [ ] **Step 3: Write the workspace module**

```python
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
        destination = target / child.name
        if child.is_dir():
            shutil.copytree(child, destination)
        else:
            shutil.copy2(child, destination)


def cleanup_workspace(path: Path) -> None:
    if path.exists():
        shutil.rmtree(path)
```

- [ ] **Step 4: Run the workspace tests to verify they pass**

Run: `pytest tests/test_refine_workspace.py -q`  
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add tests/test_refine_workspace.py python_harness/refine_workspace.py
git commit -m "feat: add refine workspace isolation helpers"
```

### Task 3: Add Suggestion Applier Boundary

**Files:**
- Create: `python_harness/refine_apply.py`
- Create: `tests/test_refine_engine.py`

- [ ] **Step 1: Write the first failing engine test around retries**

```python
from pathlib import Path

from python_harness.refine_apply import NullSuggestionApplier
from python_harness.refine_engine import execute_candidate
from python_harness.refine_models import Candidate


class FlakyApplier:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def apply(
        self,
        workspace: Path,
        suggestion: dict[str, str],
        failure_feedback: str = "",
    ) -> dict[str, object]:
        self.calls.append(failure_feedback)
        return {"ok": True, "touched_files": ["module.py"], "failure_reason": ""}


def test_execute_candidate_passes_failure_feedback_on_retry(tmp_path: Path) -> None:
    baseline = Candidate(
        id="baseline",
        parent_id=None,
        depth=0,
        workspace=tmp_path / "baseline",
        suggestion_trace=(),
    )
    baseline.workspace.mkdir()
    applier = FlakyApplier()
    feedback_seen: list[str] = []

    def self_check(_: Path) -> tuple[bool, str]:
        if not feedback_seen:
            feedback_seen.append("first")
            return False, "pytest failed"
        return True, ""

    def evaluator(_: Path) -> dict[str, object]:
        return {
            "hard_evaluation": {"all_passed": True},
            "qc_evaluation": {"all_passed": True, "failures": []},
            "soft_evaluation": {"understandability_score": 88.0},
            "final_report": {"verdict": "Pass", "suggestions": []},
        }

    candidate = execute_candidate(
        parent=baseline,
        candidate_id="c1",
        suggestion={"title": "Improve readability", "description": "Split helper"},
        workspace_root=tmp_path / "runs",
        applier=applier,
        self_check_runner=self_check,
        evaluator_runner=evaluator,
        max_retries=2,
    )

    assert candidate.status == "measured"
    assert applier.calls == ["", "pytest failed"]
    assert candidate.retry_count == 1
```

- [ ] **Step 2: Run the engine test to verify it fails**

Run: `pytest tests/test_refine_engine.py::test_execute_candidate_passes_failure_feedback_on_retry -q`  
Expected: FAIL with `ModuleNotFoundError` or missing `execute_candidate`

- [ ] **Step 3: Write the suggestion applier boundary**

```python
from pathlib import Path
from typing import Any


class NullSuggestionApplier:
    def apply(
        self,
        workspace: Path,
        suggestion: dict[str, str],
        failure_feedback: str = "",
    ) -> dict[str, Any]:
        return {
            "ok": True,
            "touched_files": [],
            "failure_reason": "",
            "suggestion_title": suggestion.get("title", ""),
            "failure_feedback": failure_feedback,
        }
```

- [ ] **Step 4: Add the minimal candidate execution function**

```python
from pathlib import Path
from typing import Any, Callable

from python_harness.refine_models import Candidate
from python_harness.refine_workspace import create_candidate_workspace


def execute_candidate(
    *,
    parent: Candidate,
    candidate_id: str,
    suggestion: dict[str, str],
    workspace_root: Path,
    applier: Any,
    self_check_runner: Callable[[Path], tuple[bool, str]],
    evaluator_runner: Callable[[Path], dict[str, Any]],
    max_retries: int,
) -> Candidate:
    workspace = create_candidate_workspace(parent.workspace, workspace_root, candidate_id)
    feedback = ""
    retries = 0
    while True:
        result = applier.apply(workspace, suggestion, failure_feedback=feedback)
        ok, feedback = self_check_runner(workspace)
        if ok:
            evaluation = evaluator_runner(workspace)
            return Candidate(
                id=candidate_id,
                parent_id=parent.id,
                depth=parent.depth + 1,
                workspace=workspace,
                suggestion_trace=parent.suggestion_trace + (suggestion["title"],),
                evaluation=evaluation,
                status="measured",
                retry_count=retries,
            )
        retries += 1
        if retries > max_retries:
            return Candidate(
                id=candidate_id,
                parent_id=parent.id,
                depth=parent.depth + 1,
                workspace=workspace,
                suggestion_trace=parent.suggestion_trace + (suggestion["title"],),
                status="failed",
                retry_count=retries - 1,
                selection_reason=str(result.get("failure_reason", feedback)),
            )
```

- [ ] **Step 5: Run the retry test to verify it passes**

Run: `pytest tests/test_refine_engine.py::test_execute_candidate_passes_failure_feedback_on_retry -q`  
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add python_harness/refine_apply.py python_harness/refine_engine.py tests/test_refine_engine.py
git commit -m "feat: add refine candidate execution boundary"
```

### Task 4: Implement Single-Round Refine Orchestration

**Files:**
- Modify: `python_harness/refine_engine.py`
- Modify: `tests/test_refine_engine.py`

- [ ] **Step 1: Add failing tests for baseline, first layer, second layer, and all-level selection**

```python
from pathlib import Path

from python_harness.refine_engine import run_refine_round
from python_harness.refine_models import Candidate


def test_run_refine_round_creates_three_first_layer_and_nine_second_layer(tmp_path: Path) -> None:
    target = tmp_path / "baseline"
    target.mkdir()
    (target / "sample.py").write_text("print('baseline')\n")

    def evaluator(workspace: Path) -> dict[str, object]:
        name = workspace.name
        if name == "baseline":
            return {
                "hard_evaluation": {"all_passed": True},
                "qc_evaluation": {"all_passed": True, "failures": []},
                "soft_evaluation": {"understandability_score": 80.0},
                "final_report": {
                    "verdict": "Fail",
                    "suggestions": [
                        {"title": "S1", "description": "d1"},
                        {"title": "S2", "description": "d2"},
                        {"title": "S3", "description": "d3"},
                    ],
                },
            }
        if name.startswith("l1-"):
            return {
                "hard_evaluation": {"all_passed": True},
                "qc_evaluation": {"all_passed": True, "failures": []},
                "soft_evaluation": {"understandability_score": 82.0},
                "final_report": {
                    "verdict": "Fail",
                    "suggestions": [
                        {"title": f"{name}-A", "description": "x"},
                        {"title": f"{name}-B", "description": "x"},
                        {"title": f"{name}-C", "description": "x"},
                    ],
                },
            }
        return {
            "hard_evaluation": {"all_passed": True},
            "qc_evaluation": {"all_passed": True, "failures": []},
            "soft_evaluation": {"understandability_score": 90.0},
            "final_report": {"verdict": "Pass", "suggestions": []},
        }

    def applier(_: Path, suggestion: dict[str, str], failure_feedback: str = "") -> dict[str, object]:
        return {"ok": True, "touched_files": [suggestion["title"]], "failure_reason": ""}

    result = run_refine_round(
        target_path=target,
        workspace_root=tmp_path / "runs",
        evaluator_runner=evaluator,
        applier=type("Applier", (), {"apply": staticmethod(applier)})(),
        self_check_runner=lambda _: (True, ""),
        max_retries=0,
    )

    assert result.baseline.id == "baseline"
    assert len([c for c in result.candidates if c.depth == 1]) == 3
    assert len([c for c in result.candidates if c.depth == 2]) == 9
```

- [ ] **Step 2: Run the round tests to verify they fail**

Run: `pytest tests/test_refine_engine.py -q`  
Expected: FAIL with missing `run_refine_round` or incorrect candidate counts

- [ ] **Step 3: Implement the minimal single-round engine**

```python
from pathlib import Path
from typing import Any, Callable

from python_harness.refine_models import Candidate, RefineRoundResult
from python_harness.refine_scoring import select_best_candidate


def _suggestions_from(evaluation: dict[str, Any]) -> list[dict[str, str]]:
    final_report = evaluation.get("final_report", {})
    return list(final_report.get("suggestions", []))


def run_refine_round(
    *,
    target_path: Path,
    workspace_root: Path,
    evaluator_runner: Callable[[Path], dict[str, Any]],
    applier: Any,
    self_check_runner: Callable[[Path], tuple[bool, str]],
    max_retries: int,
) -> RefineRoundResult:
    baseline = Candidate(
        id="baseline",
        parent_id=None,
        depth=0,
        workspace=target_path,
        suggestion_trace=(),
        evaluation=evaluator_runner(target_path),
        status="measured",
    )
    round_result = RefineRoundResult(baseline=baseline)
    first_layer: list[Candidate] = []
    for index, suggestion in enumerate(_suggestions_from(baseline.evaluation), start=1):
        candidate = execute_candidate(
            parent=baseline,
            candidate_id=f"l1-{index}",
            suggestion=suggestion,
            workspace_root=workspace_root,
            applier=applier,
            self_check_runner=self_check_runner,
            evaluator_runner=evaluator_runner,
            max_retries=max_retries,
        )
        round_result.candidates.append(candidate)
        first_layer.append(candidate)
    for parent in first_layer:
        if parent.status != "measured" or not parent.evaluation:
            continue
        for index, suggestion in enumerate(_suggestions_from(parent.evaluation), start=1):
            candidate = execute_candidate(
                parent=parent,
                candidate_id=f"{parent.id}-l2-{index}",
                suggestion=suggestion,
                workspace_root=workspace_root,
                applier=applier,
                self_check_runner=self_check_runner,
                evaluator_runner=evaluator_runner,
                max_retries=max_retries,
            )
            round_result.candidates.append(candidate)
    selection = select_best_candidate([baseline, *round_result.candidates])
    round_result.winner = selection.winner
    round_result.stop_reason = selection.reason
    return round_result
```

- [ ] **Step 4: Run the round tests to verify they pass**

Run: `pytest tests/test_refine_engine.py -q`  
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add python_harness/refine_engine.py tests/test_refine_engine.py
git commit -m "feat: add single-round refine orchestration"
```

### Task 5: Wire CLI To The Refine Engine

**Files:**
- Modify: `tests/test_cli.py`
- Modify: `python_harness/cli.py`

- [ ] **Step 1: Add failing CLI tests for new refine options and engine delegation**

```python
from typer.testing import CliRunner

from python_harness.cli import app
import python_harness.cli as cli_module

runner = CliRunner()


def test_refine_delegates_to_engine(monkeypatch) -> None:
    captured: dict[str, object] = {}

    def fake_run_refine(**kwargs):
        captured.update(kwargs)
        return {
            "rounds_completed": 1,
            "winner_id": "l1-1",
            "stop_reason": "winner improved baseline",
        }

    monkeypatch.setattr(cli_module, "run_refine", fake_run_refine)
    result = runner.invoke(
        app,
        ["refine", ".", "--max-retries", "2", "--loop", "--max-rounds", "4"],
    )

    assert result.exit_code == 0
    assert captured["max_retries"] == 2
    assert captured["loop"] is True
    assert captured["max_rounds"] == 4
    assert "winner_id" in result.stdout
```

- [ ] **Step 2: Run the CLI refine tests to verify they fail**

Run: `pytest tests/test_cli.py -k refine -q`  
Expected: FAIL because `run_refine` is not imported or the CLI still uses `steps`

- [ ] **Step 3: Update the CLI**

```python
from pathlib import Path

from python_harness.refine_engine import run_refine


@app.command()
def refine(
    path: str = typer.Argument(".", help="The path to evaluate and evolve"),
    max_retries: int = typer.Option(3, help="Maximum retries per candidate"),
    loop: bool = typer.Option(False, help="Keep refining winners across rounds"),
    max_rounds: int = typer.Option(3, help="Maximum refine rounds when looping"),
) -> None:
    console.print(
        f"[bold magenta]Starting refine for path:[/bold magenta] {path} "
        f"[dim](loop={loop}, max_rounds={max_rounds}, max_retries={max_retries})[/dim]"
    )
    result = run_refine(
        target_path=Path(path),
        max_retries=max_retries,
        loop=loop,
        max_rounds=max_rounds,
    )
    console.print(f"[green]winner_id:[/green] {result['winner_id']}")
    console.print(f"[cyan]rounds_completed:[/cyan] {result['rounds_completed']}")
    console.print(f"[yellow]stop_reason:[/yellow] {result['stop_reason']}")
```

- [ ] **Step 4: Run the CLI refine tests to verify they pass**

Run: `pytest tests/test_cli.py -k refine -q`  
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add tests/test_cli.py python_harness/cli.py
git commit -m "feat: wire cli refine command to engine"
```

### Task 6: Add Looping, Adoption, And Stop Conditions

**Files:**
- Modify: `tests/test_refine_engine.py`
- Modify: `python_harness/refine_engine.py`
- Modify: `python_harness/refine_workspace.py`

- [ ] **Step 1: Add failing tests for loop stop conditions and winner adoption**

```python
from pathlib import Path

from python_harness.refine_engine import run_refine


def test_run_refine_stops_when_winner_does_not_improve(tmp_path: Path) -> None:
    target = tmp_path / "target"
    target.mkdir()
    (target / "sample.py").write_text("print('baseline')\n")

    def evaluator(_: Path) -> dict[str, object]:
        return {
            "hard_evaluation": {"all_passed": True},
            "qc_evaluation": {"all_passed": True, "failures": []},
            "soft_evaluation": {"understandability_score": 80.0},
            "final_report": {
                "verdict": "Fail",
                "suggestions": [],
            },
            "metrics": {
                "avg_mi": 70.0,
                "qa_score": 80.0,
                "cc_issue_count": 0,
                "hard_failed": False,
                "qc_failed": False,
            },
        }

    result = run_refine(
        target_path=target,
        max_retries=0,
        loop=True,
        max_rounds=3,
        evaluator_runner=evaluator,
    )

    assert result["rounds_completed"] == 1
    assert result["stop_reason"] == "winner has no suggestions"
```

- [ ] **Step 2: Run the loop tests to verify they fail**

Run: `pytest tests/test_refine_engine.py -k "run_refine or adopt" -q`  
Expected: FAIL because `run_refine` does not stop cleanly on empty suggestions or adopt the winner yet

- [ ] **Step 3: Implement loop orchestration and adoption**

```python
from pathlib import Path
from typing import Any, Callable

from python_harness.evaluator import Evaluator
from python_harness.refine_apply import NullSuggestionApplier
from python_harness.refine_scoring import build_candidate_rank
from python_harness.refine_workspace import adopt_candidate_workspace


def _default_evaluator_runner(path: Path) -> dict[str, Any]:
    return Evaluator(str(path)).run()


def _default_self_check_runner(_: Path) -> tuple[bool, str]:
    return True, ""


def run_refine(
    *,
    target_path: Path,
    max_retries: int,
    loop: bool,
    max_rounds: int,
    evaluator_runner: Callable[[Path], dict[str, Any]] | None = None,
    applier: Any | None = None,
    self_check_runner: Callable[[Path], tuple[bool, str]] | None = None,
) -> dict[str, Any]:
    evaluator_runner = evaluator_runner or _default_evaluator_runner
    applier = applier or NullSuggestionApplier()
    self_check_runner = self_check_runner or _default_self_check_runner
    previous_baseline_rank = None
    rounds_completed = 0
    winner_id = "baseline"
    stop_reason = "max rounds reached"
    workspace_root = target_path.parent / ".harness-refine"

    while rounds_completed < max_rounds:
        round_result = run_refine_round(
            target_path=target_path,
            workspace_root=workspace_root,
            evaluator_runner=evaluator_runner,
            applier=applier,
            self_check_runner=self_check_runner,
            max_retries=max_retries,
        )
        rounds_completed += 1
        assert round_result.winner is not None
        winner = round_result.winner
        winner_id = winner.id
        winner_rank = build_candidate_rank(winner)
        if winner.workspace != target_path:
            adopt_candidate_workspace(winner.workspace, target_path)
        if previous_baseline_rank is not None and winner_rank <= previous_baseline_rank:
            stop_reason = "winner did not improve baseline"
            break
        suggestions = (
            (winner.evaluation or {}).get("final_report", {}).get("suggestions", [])
        )
        if not loop:
            stop_reason = "single round completed"
            break
        if not suggestions:
            stop_reason = "winner has no suggestions"
            break
        previous_baseline_rank = winner_rank
    return {
        "rounds_completed": rounds_completed,
        "winner_id": winner_id,
        "stop_reason": stop_reason,
    }
```

- [ ] **Step 4: Run the loop tests to verify they pass**

Run: `pytest tests/test_refine_engine.py -k "run_refine or adopt" -q`  
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add python_harness/refine_engine.py python_harness/refine_workspace.py tests/test_refine_engine.py
git commit -m "feat: add refine loop orchestration and winner adoption"
```

### Task 7: Finish Self-Check Integration And Full Validation

**Files:**
- Modify: `python_harness/refine_engine.py`
- Modify: `tests/test_refine_engine.py`

- [ ] **Step 1: Add a failing test proving self-check failure blocks full measure**

```python
from pathlib import Path

from python_harness.refine_engine import execute_candidate
from python_harness.refine_models import Candidate


def test_execute_candidate_does_not_measure_failed_candidate(tmp_path: Path) -> None:
    baseline = Candidate(
        id="baseline",
        parent_id=None,
        depth=0,
        workspace=tmp_path / "baseline",
        suggestion_trace=(),
    )
    baseline.workspace.mkdir()
    measured: list[str] = []

    def evaluator(workspace: Path) -> dict[str, object]:
        measured.append(workspace.name)
        return {"final_report": {"verdict": "Fail", "suggestions": []}}

    class StaticApplier:
        def apply(self, workspace: Path, suggestion: dict[str, str], failure_feedback: str = "") -> dict[str, object]:
            return {"ok": True, "touched_files": [], "failure_reason": ""}

    candidate = execute_candidate(
        parent=baseline,
        candidate_id="blocked",
        suggestion={"title": "Fix tests", "description": "d"},
        workspace_root=tmp_path / "runs",
        applier=StaticApplier(),
        self_check_runner=lambda _: (False, "pytest failed"),
        evaluator_runner=evaluator,
        max_retries=0,
    )

    assert candidate.status == "failed"
    assert measured == []
```

- [ ] **Step 2: Run the self-check test to verify it fails if behavior regressed**

Run: `pytest tests/test_refine_engine.py::test_execute_candidate_does_not_measure_failed_candidate -q`  
Expected: PASS after the implementation is corrected

- [ ] **Step 3: Replace the default self-check stub with real commands**

```python
import subprocess


def _run_command(path: Path, args: list[str]) -> tuple[bool, str]:
    completed = subprocess.run(
        args,
        cwd=path,
        capture_output=True,
        text=True,
        check=False,
    )
    output = completed.stdout + completed.stderr
    return completed.returncode == 0, output.strip()


def _default_self_check_runner(path: Path) -> tuple[bool, str]:
    checks = [
        ["ruff", "check", "."],
        ["mypy", "python_harness", "tests"],
        ["pytest", "-q"],
    ]
    for args in checks:
        ok, output = _run_command(path, args)
        if not ok:
            return False, output
    return True, ""
```

- [ ] **Step 4: Run targeted refine tests**

Run: `pytest tests/test_refine_scoring.py tests/test_refine_workspace.py tests/test_refine_engine.py -q`  
Expected: PASS

- [ ] **Step 5: Run project self-checks**

Run: `ruff check .`  
Expected: PASS

Run: `mypy python_harness tests`  
Expected: PASS

Run: `pytest -q`  
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add python_harness/refine_engine.py tests/test_refine_engine.py
git commit -m "feat: finalize refine self-check integration"
```

## Self-Review

- Spec coverage: the plan covers the fixed two-level `3 + 9` expansion, all-level selection, isolated workspaces, retry policy, CLI redesign, loop stopping conditions, and tests
- Placeholder scan: no `TODO`, `TBD`, or vague "handle appropriately" language remains
- Type consistency: the plan uses one stable API surface for `Candidate`, `SelectionResult`, `RefineRoundResult`, `execute_candidate`, `run_refine_round`, and `run_refine`

## Notes For The Implementer

- Reuse `Evaluator.run()` for full measure whenever possible instead of manually stitching hard, QC, and soft evaluation
- Reuse `soft_eval_report.extract_metrics()` from `python_harness/soft_eval_report.py` for ranking inputs instead of duplicating threshold logic
- Keep `cli.py` thin; if it starts gaining refine helper functions again, move them back into `refine_engine.py`
- Do not introduce Git-branch orchestration in this milestone; the approved design explicitly treats workspaces as sandboxes
