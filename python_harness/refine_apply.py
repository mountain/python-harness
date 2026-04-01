from pathlib import Path
from typing import Any, cast

from python_harness.llm_client import build_llm_client, load_llm_settings
from python_harness.refine_apply_support import (
    build_messages,
    parse_updates,
    select_editable_files,
)


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


class LLMSuggestionApplier:
    def __init__(
        self,
        client: Any | None = None,
        model_name: str | None = None,
    ) -> None:
        settings = load_llm_settings()
        self.client = client if client is not None else build_llm_client(settings)
        self.model_name = model_name or settings.mini_model_name
        self.request_timeout_seconds = settings.request_timeout_seconds

    def apply(
        self,
        workspace: Path,
        suggestion: dict[str, str],
        failure_feedback: str = "",
    ) -> dict[str, Any]:
        if self.client is None:
            return {
                "ok": False,
                "touched_files": [],
                "failure_reason": "LLM_API_KEY not configured",
            }
        files = select_editable_files(workspace, suggestion, failure_feedback)
        if not files:
            return {
                "ok": False,
                "touched_files": [],
                "failure_reason": "No editable files selected for suggestion",
            }

        client = cast(Any, self.client)
        try:
            completion = client.chat.completions.create(
                model=self.model_name,
                messages=build_messages(
                    workspace,
                    suggestion,
                    failure_feedback,
                    files,
                ),
                response_format={"type": "json_object"},
                timeout=self.request_timeout_seconds,
            )
        except Exception as exc:
            return {
                "ok": False,
                "touched_files": [],
                "failure_reason": str(exc),
                "retryable": False,
            }
        content = completion.choices[0].message.content
        if not content:
            return {
                "ok": False,
                "touched_files": [],
                "failure_reason": "LLM returned empty response",
                "retryable": False,
            }

        try:
            updates = parse_updates(content)
            touched_files: list[str] = []
            for update in updates:
                destination = (workspace / update["path"]).resolve()
                if not destination.is_relative_to(workspace.resolve()):
                    raise ValueError("LLM update path is outside workspace")
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_text(update["content"], encoding="utf-8")
                touched_files.append(str(destination.relative_to(workspace)))
        except Exception as exc:
            return {
                "ok": False,
                "touched_files": [],
                "failure_reason": str(exc),
                "retryable": False,
            }

        return {
            "ok": True,
            "touched_files": touched_files,
            "failure_reason": "",
            "suggestion_title": suggestion.get("title", ""),
            "failure_feedback": failure_feedback,
            "workspace": str(workspace),
        }
