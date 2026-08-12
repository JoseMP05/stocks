from __future__ import annotations

import anthropic

from app.llm.errors import LLMError


class AnthropicProvider:
    def __init__(self, model: str, api_key: str) -> None:
        self._model = model
        self._api_key = api_key

    def analyze(self, prompt: str) -> str:
        if not self._api_key:
            raise LLMError("Falta la API key de Anthropic. Configurala en Ajustes.")
        client = anthropic.Anthropic(api_key=self._api_key)
        try:
            response = client.messages.create(
                model=self._model,
                max_tokens=2048,
                messages=[{"role": "user", "content": prompt}],
            )
        except anthropic.AuthenticationError as exc:
            raise LLMError("La API key de Anthropic fue rechazada.") from exc
        except anthropic.APIError as exc:
            raise LLMError(f"Anthropic no pudo responder: {exc}") from exc
        return "".join(block.text for block in response.content if block.type == "text")
