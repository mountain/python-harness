import json
from pathlib import Path
from typing import Any

from python_harness.refine_apply import LLMSuggestionApplier


class FakeCompletionMessage:
    def __init__(self, content: str) -> None:
        self.content = content


class FakeCompletionChoice:
    def __init__(self, content: str) -> None:
        self.message = FakeCompletionMessage(content)


class FakeCompletionResponse:
    def __init__(self, content: str) -> None:
        self.choices = [FakeCompletionChoice(content)]


class FakeChatCompletions:
    def __init__(self, payload: str) -> None:
        self.payload = payload
        self.calls: list[dict[str, Any]] = []

    def create(self, **kwargs: Any) -> FakeCompletionResponse:
        self.calls.append(kwargs)
        return FakeCompletionResponse(self.payload)


class FakeClient:
    def __init__(self, payload: str) -> None:
        fake_chat = type(
            "FakeChat",
            (),
            {"completions": FakeChatCompletions(payload)},
        )
        self.chat = fake_chat()


def test_llm_suggestion_applier_writes_workspace_updates(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    target = workspace / "module.py"
    target.write_text("def value() -> int:\n    return 1\n")
    payload = json.dumps(
        {
            "summary": "updated module",
            "updates": [
                {
                    "path": "module.py",
                    "content": "def value() -> int:\n    return 2\n",
                }
            ],
        }
    )
    applier = LLMSuggestionApplier(
        client=FakeClient(payload),
        model_name="test-model",
    )

    result = applier.apply(
        workspace,
        {
            "title": "Raise value",
            "description": "Update the function return value",
            "target_file": "module.py",
        },
    )

    assert result["ok"] is True
    assert result["touched_files"] == ["module.py"]
    assert target.read_text() == "def value() -> int:\n    return 2\n"


def test_llm_suggestion_applier_rejects_updates_outside_workspace(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "module.py").write_text("def value() -> int:\n    return 1\n")
    payload = json.dumps(
        {
            "summary": "bad path",
            "updates": [
                {
                    "path": "../escape.py",
                    "content": "print('escape')\n",
                }
            ],
        }
    )
    applier = LLMSuggestionApplier(
        client=FakeClient(payload),
        model_name="test-model",
    )

    result = applier.apply(
        workspace,
        {
            "title": "Bad write",
            "description": "Try writing outside workspace",
            "target_file": "module.py",
        },
    )

    assert result["ok"] is False
    assert "outside workspace" in str(result["failure_reason"])
