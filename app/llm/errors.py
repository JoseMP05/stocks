"""Error raised when a provider call fails, carrying a message safe to show in the UI."""

from __future__ import annotations


class LLMError(Exception):
    pass
