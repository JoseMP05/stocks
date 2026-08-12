"""LLM providers for the optional AI interpretation of an analysis run."""

from __future__ import annotations

import os

from app.llm.base import LLMProvider
from app.models import LLMSettings

_OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"


def get_provider(settings: LLMSettings) -> LLMProvider:
    if settings.provider == "anthropic":
        from app.llm.anthropic_provider import AnthropicProvider

        return AnthropicProvider(model=settings.model, api_key=_resolve_key(settings, "ANTHROPIC_API_KEY"))

    from app.llm.openai_compatible import OpenAICompatibleProvider

    if settings.provider == "openrouter":
        return OpenAICompatibleProvider(
            model=settings.model,
            api_key=_resolve_key(settings, "OPENROUTER_API_KEY"),
            label="OpenRouter",
            base_url=_OPENROUTER_BASE_URL,
            # Optional per OpenRouter's docs — used only for their leaderboards.
            default_headers={"X-OpenRouter-Title": "Análisis de Acciones"},
        )

    return OpenAICompatibleProvider(
        model=settings.model,
        api_key=_resolve_key(settings, "OPENAI_API_KEY"),
        label="OpenAI",
    )


def _resolve_key(settings: LLMSettings, env_var: str) -> str:
    """Environment variable wins over the key saved from the UI."""
    return os.environ.get(env_var) or settings.api_key
