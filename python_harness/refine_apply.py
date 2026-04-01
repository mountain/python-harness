import json
from pathlib import Path
from typing import Any, cast

from python_harness.llm_client import build_llm_client, load_llm_settings
from python_harness.python_file_inventory import collect_python_files


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
        self.model_name = model_name or settings.model_name

    def _select_files(self, workspace: Path, suggestion: dict[str, str]) -> list[Path]:
        target_file = suggestion.get("target_file", "").strip()
        if target_file and target_file != "all":
            target_path = workspace / target_file
            if target_path.is_file():
                return [target_path]
            if target_path.is_dir():
                return sorted(target_path.rglob("*.py"))[:3]
        return collect_python_files(workspace)[:3]

    def _build_messages(
        self,
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
        system_prompt = (
            "You apply a single repository improvement suggestion. "
            "Return only valid JSON with schema "
            '{"updates":[{"path":"relative/path.py","content":"full file content"}]}. '
            "Make the smallest possible change that satisfies the suggestion "
            "and preserves behavior. "
            "Never write files outside the workspace."
        )
        user_prompt = (
            f"Suggestion title: {suggestion.get('title', '')}\n"
            f"Suggestion description: {suggestion.get('description', '')}\n"
            f"Suggestion target_file: {suggestion.get('target_file', 'all')}\n"
            f"Failure feedback from previous attempt: {failure_feedback or 'None'}\n\n"
            f"Workspace python inventory:\n{inventory}\n\n"
            f"Editable file contents:\n{file_blocks}"
        )
        return [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

    def _parse_updates(self, raw_content: str) -> list[dict[str, str]]:
        payload = json.loads(raw_content)
        updates = payload.get("updates", [])
        if not isinstance(updates, list):
            raise ValueError("LLM updates payload must contain a list")
        parsed: list[dict[str, str]] = []
        for update in updates:
            if not isinstance(update, dict):
                continue
            path = update.get("path")
            content = update.get("content")
            if isinstance(path, str) and isinstance(content, str):
                parsed.append({"path": path, "content": content})
        if not parsed:
            raise ValueError("LLM returned no file updates")
        return parsed

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
        files = self._select_files(workspace, suggestion)
        if not files:
            return {
                "ok": False,
                "touched_files": [],
                "failure_reason": "No editable files selected for suggestion",
            }

        client = cast(Any, self.client)
        completion = client.chat.completions.create(
            model=self.model_name,
            messages=self._build_messages(
                workspace,
                suggestion,
                failure_feedback,
                files,
            ),
            response_format={"type": "json_object"},
        )
        content = completion.choices[0].message.content
        if not content:
            return {
                "ok": False,
                "touched_files": [],
                "failure_reason": "LLM returned empty response",
            }

        try:
            updates = self._parse_updates(content)
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
            }

        return {
            "ok": True,
            "touched_files": touched_files,
            "failure_reason": "",
            "suggestion_title": suggestion.get("title", ""),
            "failure_feedback": failure_feedback,
            "workspace": str(workspace),
        }
