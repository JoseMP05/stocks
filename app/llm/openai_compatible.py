"""Provider for any service that speaks the OpenAI chat-completions format.

OpenAI itself and OpenRouter both fit here — same wire format, only the
base URL (and, for OpenRouter, a couple of attribution headers) differ.
"""

from __future__ import annotations

import openai

from app.llm.errors import LLMError


class OpenAICompatibleProvider:
    def __init__(
        self,
        model: str,
        api_key: str,
        label: str,
        base_url: str | None = None,
        default_headers: dict[str, str] | None = None,
    ) -> None:
        self._model = model
        self._api_key = api_key
        self._label = label
        self._base_url = base_url
        self._default_headers = default_headers

    def analyze(self, prompt: str) -> str:
        if not self._api_key:
            raise LLMError(f"Falta la API key de {self._label}. Configurala en Ajustes.")
        client = openai.OpenAI(
            api_key=self._api_key,
            base_url=self._base_url,
            default_headers=self._default_headers,
        )
        try:
            response = client.chat.completions.create(
                model=self._model,
                messages=[{"role": "user", "content": prompt}],
            )
        except openai.AuthenticationError as exc:
            raise LLMError(f"La API key de {self._label} fue rechazada.") from exc
        except openai.APIError as exc:
            raise LLMError(f"{self._label} no pudo responder: {exc}") from exc
        except Exception as exc:  # noqa: BLE001 — a provider fault must never 500 the UI
            raise LLMError(f"Fallo al llamar a {self._label}: {exc}") from exc
        return response.choices[0].message.content or ""
