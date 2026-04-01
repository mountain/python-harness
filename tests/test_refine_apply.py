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


def test_llm_suggestion_applier_passes_request_timeout(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "module.py").write_text("def value() -> int:\n    return 1\n")
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
    client = FakeClient(payload)
    applier = LLMSuggestionApplier(
        client=client,
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
    calls = client.chat.completions.calls
    assert len(calls) == 1
    assert calls[0]["timeout"] == 60.0


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


def test_llm_suggestion_applier_defaults_to_mini_model(
    monkeypatch: Any,
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "module.py").write_text("def value() -> int:\n    return 1\n")
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
    monkeypatch.setenv("LLM_MODEL_NAME", "reasoner-model")
    monkeypatch.setenv("LLM_MINI_MODEL_NAME", "mini-model")
    applier = LLMSuggestionApplier(client=FakeClient(payload))

    result = applier.apply(
        workspace,
        {
            "title": "Raise value",
            "description": "Update the function return value",
            "target_file": "module.py",
        },
    )

    assert result["ok"] is True
    assert applier.client is not None
    calls = applier.client.chat.completions.calls
    assert len(calls) == 1
    assert calls[0]["model"] == "mini-model"


def test_llm_suggestion_applier_includes_failed_file_in_retry_context(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "target.py").write_text("def target() -> int:\n    return 1\n")
    failed = workspace / "broken.py"
    failed.write_text("def broken() -> str:\n    return value\n")
    (workspace / "other.py").write_text("def other() -> int:\n    return 3\n")
    payload = json.dumps(
        {
            "summary": "updated module",
            "updates": [
                {
                    "path": "target.py",
                    "content": "def target() -> int:\n    return 2\n",
                }
            ],
        }
    )
    client = FakeClient(payload)
    applier = LLMSuggestionApplier(
        client=client,
        model_name="test-model",
    )

    result = applier.apply(
        workspace,
        {
            "title": "Raise value",
            "description": "Update the function return value",
            "target_file": "target.py",
        },
        failure_feedback='broken.py:1: error: Name "value" is not defined',
    )

    assert result["ok"] is True
    user_prompt = client.chat.completions.calls[0]["messages"][1]["content"]
    assert "FILE: target.py" in user_prompt
    assert "FILE: broken.py" in user_prompt
    assert "FILE: other.py" not in user_prompt


def test_llm_suggestion_applier_prompt_blocks_comment_churn(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "module.py").write_text("def value() -> int:\n    return 1\n")
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
    client = FakeClient(payload)
    applier = LLMSuggestionApplier(
        client=client,
        model_name="test-model",
    )

    result = applier.apply(
        workspace,
        {
            "title": "Raise value",
            "description": "Update the function return value",
            "target_file": "module.py",
        },
        failure_feedback="module.py:1: error: bad return type",
    )

    assert result["ok"] is True
    system_prompt = client.chat.completions.calls[0]["messages"][0]["content"]
    assert "Do not rewrite comments, docstrings, or unrelated imports" in system_prompt
