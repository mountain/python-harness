import os
from dataclasses import dataclass
from typing import Any

from openai import OpenAI


@dataclass(frozen=True)
class LLMSettings:
    api_key: str | None
    base_url: str
    model_name: str
    mini_model_name: str


def load_llm_settings() -> LLMSettings:
    return LLMSettings(
        api_key=os.environ.get("LLM_API_KEY"),
        base_url=os.environ.get("LLM_BASE_URL", "https://api.deepseek.com/v1"),
        model_name=os.environ.get("LLM_MODEL_NAME", "deepseek-reasoner"),
        mini_model_name=os.environ.get("LLM_MINI_MODEL_NAME", "deepseek-chat"),
    )


def build_llm_client(settings: LLMSettings) -> Any | None:
    if not settings.api_key:
        return None
    return OpenAI(api_key=settings.api_key, base_url=settings.base_url)
