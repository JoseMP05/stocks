"""Contract every LLM provider implements."""

from __future__ import annotations

from typing import Protocol


class LLMProvider(Protocol):
    def analyze(self, prompt: str) -> str: ...
