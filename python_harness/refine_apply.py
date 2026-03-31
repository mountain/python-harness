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
            "workspace": str(workspace),
        }
