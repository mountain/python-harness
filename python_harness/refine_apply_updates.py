import json


def parse_updates(raw_content: str) -> list[dict[str, str]]:
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
