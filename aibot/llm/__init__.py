"""
LLM providers behind one interface, created lazily by name.
"""
from collections.abc import Callable

from aibot.llm.base import (
    LLMProvider,
    LLMResponse,
    Message,
    ProviderError,
    ProviderNotConfigured,
    ToolCall,
    ToolSpec,
)
from aibot.llm.gemini import GeminiProvider
from aibot.llm.local import LocalProvider
from aibot.llm.openai_compat import PRESETS, OpenAICompatProvider
from aibot.llm.puter import PuterProvider

__all__ = [
    "LLMProvider",
    "LLMResponse",
    "Message",
    "ProviderError",
    "ProviderNotConfigured",
    "ProviderRegistry",
    "ToolCall",
    "ToolSpec",
]

# Older names still accepted in configs and requests.
ALIASES = {
    "vertex_ai": "gemini",
    "vertex": "gemini",
    "google": "gemini",
    "puter_ai": "puter",
    "default": "local",
}


def _factories() -> dict[str, Callable[[], LLMProvider]]:
    factories: dict[str, Callable[[], LLMProvider]] = {
        "gemini": GeminiProvider.from_env,
        "puter": PuterProvider.from_env,
        "local": LocalProvider,
    }
    for name in PRESETS:
        factories[name] = lambda name=name: OpenAICompatProvider.from_env(name)
    return factories


class ProviderRegistry:
    """Creates each provider on first use and keeps it for the app's lifetime."""

    def __init__(self) -> None:
        self._factories = _factories()
        self._instances: dict[str, LLMProvider] = {}

    @staticmethod
    def normalize(name: str) -> str:
        """Map aliases such as `vertex_ai` to the canonical provider name."""
        key = (name or "").strip().lower()
        return ALIASES.get(key, key)

    def names(self) -> list[str]:
        """Canonical names of all known providers."""
        return sorted(self._factories)

    def exists(self, name: str) -> bool:
        """True when the name (or alias) refers to a known provider."""
        return self.normalize(name) in self._factories

    def get(self, name: str) -> LLMProvider:
        """Return the provider instance for a name or alias."""
        key = self.normalize(name)
        if key not in self._instances:
            if key not in self._factories:
                raise ProviderNotConfigured(f"Unknown provider '{name}'.")
            self._instances[key] = self._factories[key]()
        return self._instances[key]

    def register(self, name: str, provider: LLMProvider) -> None:
        """Use a specific provider instance for a name (custom providers, tests)."""
        key = self.normalize(name)
        self._factories.setdefault(key, lambda: provider)
        self._instances[key] = provider

    async def aclose(self) -> None:
        """Close every provider that was created."""
        for provider in self._instances.values():
            await provider.aclose()
