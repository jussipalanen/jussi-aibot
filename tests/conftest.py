"""
Shared fixtures. AI providers are replaced with fakes, so no credentials are needed.
"""
import os
from collections.abc import Callable
from typing import Any

import pytest

# Safe defaults before any app import.
os.environ.setdefault("DEFAULT_PROVIDER", "puter_ai")
os.environ.setdefault("DISABLE_LOCAL_MODEL", "true")
os.environ.setdefault("DAILY_RATE_LIMIT", "1000/day")
for _name in ("AI_SECRET_KEY", "ALLOWED_ORIGINS", "CLIENTS_FILE", "PUTER_API_KEY", "GEMINI_API_KEY", "GOOGLE_API_KEY", "GCP_PROJECT"):
    os.environ.pop(_name, None)

from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from aibot.app import create_app  # noqa: E402
from aibot.llm import LLMProvider, LLMResponse, Message, ProviderRegistry, ToolSpec  # noqa: E402
from aibot.settings import Settings  # noqa: E402

VOCABULARY = ["helsinki", "tampere", "sauna", "office", "apartment", "balcony"]


def keyword_vector(text: str) -> list[float]:
    """A tiny deterministic 'embedding': keyword counts."""
    lowered = text.lower()
    return [float(lowered.count(word)) for word in VOCABULARY] + [0.01]


class FakeProvider(LLMProvider):
    """Returns scripted responses and records every call."""

    name = "fake"

    def __init__(self, responses: list[LLMResponse] | None = None, text: str = "fake reply",
                 supports_tools: bool = True) -> None:
        self.responses = list(responses or [])
        self.text = text
        self.supports_tools = supports_tools
        self.calls: list[dict[str, Any]] = []
        self.embed_calls: list[tuple[list[str], str]] = []

    def is_configured(self) -> bool:
        return True

    async def generate(self, messages: list[Message], *, model: str | None = None, system: str | None = None,
                       tools: list[ToolSpec] | None = None, temperature: float | None = None,
                       json_output: bool = False) -> LLMResponse:
        self.calls.append({"messages": list(messages), "model": model, "system": system, "tools": tools,
                           "json_output": json_output})
        return self.responses.pop(0) if self.responses else LLMResponse(text=self.text)

    async def embed(self, texts: list[str], *, model: str | None = None, task: str = "document") -> list[list[float]]:
        self.embed_calls.append((list(texts), task))
        return [keyword_vector(text) for text in texts]


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture
def make_app(monkeypatch: pytest.MonkeyPatch) -> Callable[..., FastAPI]:
    """Build an app with environment overrides and fake providers.

    Usage: make_app(env={"AI_SECRET_KEY": "k"}, providers={"gemini": FakeProvider()})
    """
    def factory(env: dict[str, str] | None = None, providers: dict[str, LLMProvider] | None = None) -> FastAPI:
        for key, value in (env or {}).items():
            monkeypatch.setenv(key, value)
        registry = ProviderRegistry()
        for name, provider in (providers or {}).items():
            registry.register(name, provider)
        return create_app(Settings.from_env(), registry)

    return factory


@pytest.fixture
def client(make_app: Callable[..., FastAPI]) -> TestClient:
    """A client for an app with open access and real (unconfigured) providers."""
    return TestClient(make_app(), raise_server_exceptions=False)
