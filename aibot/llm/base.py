"""
Provider-neutral types shared by every LLM provider.
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Literal

EmbeddingTask = Literal["document", "query"]


class ProviderNotConfigured(RuntimeError):
    """The provider is missing credentials or settings (maps to HTTP 503)."""


class ProviderError(RuntimeError):
    """The provider was reached but the request failed (maps to HTTP 502)."""


@dataclass
class ToolCall:
    """A tool invocation requested by the model."""

    id: str
    name: str
    arguments: dict[str, Any]


@dataclass
class ToolSpec:
    """A tool the model may call, described with a JSON Schema."""

    name: str
    description: str
    parameters: dict[str, Any]


@dataclass
class Message:
    """One chat message. `raw` keeps the provider's own message object, if any."""

    role: Literal["user", "assistant", "tool"]
    content: str = ""
    tool_calls: list[ToolCall] = field(default_factory=list)
    tool_call_id: str | None = None
    name: str | None = None
    raw: Any = None


@dataclass
class LLMResponse:
    """A model reply: final text, tool calls, or both."""

    text: str
    tool_calls: list[ToolCall] = field(default_factory=list)
    raw_message: Any = None


class LLMProvider(ABC):
    """Common interface for chat generation and embeddings."""

    name: str = ""
    supports_tools: bool = True
    supports_embeddings: bool = True

    @abstractmethod
    def is_configured(self) -> bool:
        """Return True when the provider has the credentials it needs."""

    @abstractmethod
    async def generate(
        self,
        messages: list[Message],
        *,
        model: str | None = None,
        system: str | None = None,
        tools: list[ToolSpec] | None = None,
        temperature: float | None = None,
        json_output: bool = False,
    ) -> LLMResponse:
        """Generate the next assistant message."""

    async def embed(
        self,
        texts: list[str],
        *,
        model: str | None = None,
        task: EmbeddingTask = "document",
    ) -> list[list[float]]:
        """Return one embedding vector per input text."""
        raise ProviderNotConfigured(f"Provider '{self.name}' does not support embeddings.")

    async def aclose(self) -> None:
        """Release network resources."""
