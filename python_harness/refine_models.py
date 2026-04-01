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
    suggestion: dict[str, str] | None = None
    evaluation: dict[str, Any] | None = None
    status: str = "pending"
    retry_count: int = 0
    selection_reason: str = ""
    attempt_history: list[dict[str, Any]] = field(default_factory=list)


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
