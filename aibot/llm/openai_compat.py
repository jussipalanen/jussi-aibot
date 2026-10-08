"""
Provider for any OpenAI-compatible chat completions API
(OpenAI, Groq, OpenRouter, Mistral, Ollama, ...).
"""
import json
from dataclasses import dataclass
from typing import Any

import httpx

from aibot.llm.base import (
    EmbeddingTask,
    LLMProvider,
    LLMResponse,
    Message,
    ProviderError,
    ProviderNotConfigured,
    ToolCall,
    ToolSpec,
)
from aibot.settings import env

_TIMEOUT = httpx.Timeout(60.0, connect=10.0)


@dataclass(frozen=True)
class Preset:
    """Defaults for a known OpenAI-compatible service."""

    base_url: str
    needs_key: bool = True
    model: str = ""
    embedding_model: str = ""


PRESETS: dict[str, Preset] = {
    "openai": Preset("https://api.openai.com/v1"),
    "groq": Preset("https://api.groq.com/openai/v1"),
    "openrouter": Preset("https://openrouter.ai/api/v1"),
    "mistral": Preset("https://api.mistral.ai/v1"),
    # Set OLLAMA_BASE_URL, e.g. http://localhost:11434/v1
    "ollama": Preset("", needs_key=False),
    "openai_compat": Preset(""),
}


class OpenAICompatProvider(LLMProvider):
    """Chat and embeddings over the `/chat/completions` and `/embeddings` endpoints."""

    def __init__(
        self,
        name: str,
        *,
        base_url: str,
        api_key: str = "",
        needs_key: bool = True,
        default_model: str = "",
        embedding_model: str = "",
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.name = name
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.needs_key = needs_key
        self.default_model = default_model
        self.embedding_model = embedding_model
        self._transport = transport
        self._http: httpx.AsyncClient | None = None

    @classmethod
    def from_env(cls, name: str) -> "OpenAICompatProvider":
        """Build a preset provider. `<NAME>_API_KEY`, `<NAME>_BASE_URL`,
        `<NAME>_MODEL` and `<NAME>_EMBEDDING_MODEL` override the defaults."""
        preset = PRESETS[name]
        prefix = name.upper()
        return cls(
            name,
            base_url=env(f"{prefix}_BASE_URL", preset.base_url),
            api_key=env(f"{prefix}_API_KEY"),
            needs_key=preset.needs_key,
            default_model=env(f"{prefix}_MODEL", preset.model),
            embedding_model=env(f"{prefix}_EMBEDDING_MODEL", preset.embedding_model),
        )

    def is_configured(self) -> bool:
        return bool(self.base_url) and (bool(self.api_key) or not self.needs_key)

    def _client(self) -> httpx.AsyncClient:
        if not self.is_configured():
            prefix = self.name.upper()
            raise ProviderNotConfigured(
                f"Provider '{self.name}' is not configured. Set {prefix}_API_KEY"
                f"{f' and {prefix}_BASE_URL' if not self.base_url else ''}."
            )
        if self._http is None:
            headers = {"Authorization": f"Bearer {self.api_key}"} if self.api_key else {}
            self._http = httpx.AsyncClient(
                base_url=self.base_url, headers=headers, timeout=_TIMEOUT, transport=self._transport,
            )
        return self._http

    def _model(self, model: str | None, fallback: str, kind: str) -> str:
        chosen = model or fallback
        if not chosen:
            raise ProviderNotConfigured(
                f"No {kind} set for provider '{self.name}'. Set it in the config or with "
                f"{self.name.upper()}_{'EMBEDDING_MODEL' if kind == 'embedding model' else 'MODEL'}."
            )
        return chosen

    async def _post(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        client = self._client()
        try:
            response = await client.post(path, json=payload)
        except httpx.HTTPError as exc:
            raise ProviderError(f"{self.name} request failed: {exc}") from exc
        if response.status_code >= 400:
            raise ProviderError(f"{self.name} returned HTTP {response.status_code}: {response.text[:300]}")
        try:
            return response.json()
        except ValueError as exc:
            raise ProviderError(f"{self.name} returned invalid JSON.") from exc

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
        self._client()  # report missing credentials before a missing model
        payload: dict[str, Any] = {
            "model": self._model(model, self.default_model, "model"),
            "messages": _to_openai_messages(messages, system),
        }
        if temperature is not None:
            payload["temperature"] = temperature
        if tools:
            payload["tools"] = [
                {
                    "type": "function",
                    "function": {"name": t.name, "description": t.description, "parameters": t.parameters},
                }
                for t in tools
            ]
        elif json_output:
            payload["response_format"] = {"type": "json_object"}

        data = await self._post("/chat/completions", payload)
        try:
            message = data["choices"][0]["message"]
        except (KeyError, IndexError, TypeError) as exc:
            raise ProviderError(f"{self.name} returned an unexpected response.") from exc

        tool_calls = []
        for index, call in enumerate(message.get("tool_calls") or []):
            function = call.get("function") or {}
            try:
                arguments = json.loads(function.get("arguments") or "{}")
            except json.JSONDecodeError:
                arguments = {}
            tool_calls.append(ToolCall(
                id=call.get("id") or f"call_{index}",
                name=function.get("name", ""),
                arguments=arguments if isinstance(arguments, dict) else {},
            ))
        return LLMResponse(text=(message.get("content") or "").strip(), tool_calls=tool_calls)

    async def embed(
        self,
        texts: list[str],
        *,
        model: str | None = None,
        task: EmbeddingTask = "document",
    ) -> list[list[float]]:
        if not texts:
            return []
        self._client()
        chosen = self._model(model, self.embedding_model, "embedding model")
        vectors: list[list[float]] = []
        for start in range(0, len(texts), 100):
            data = await self._post("/embeddings", {"model": chosen, "input": texts[start:start + 100]})
            rows = sorted(data.get("data") or [], key=lambda row: row.get("index", 0))
            vectors.extend(row.get("embedding") or [] for row in rows)
        if len(vectors) != len(texts):
            raise ProviderError(f"{self.name} returned an unexpected number of embeddings.")
        return vectors

    async def aclose(self) -> None:
        http, self._http = self._http, None
        if http is not None:
            await http.aclose()


def _to_openai_messages(messages: list[Message], system: str | None) -> list[dict[str, Any]]:
    """Convert neutral messages to the OpenAI chat format."""
    result: list[dict[str, Any]] = [{"role": "system", "content": system}] if system else []
    for message in messages:
        if message.role == "tool":
            result.append({"role": "tool", "tool_call_id": message.tool_call_id, "content": message.content})
        elif message.role == "assistant":
            item: dict[str, Any] = {"role": "assistant", "content": message.content or None}
            if message.tool_calls:
                item["tool_calls"] = [
                    {
                        "id": call.id,
                        "type": "function",
                        "function": {"name": call.name, "arguments": json.dumps(call.arguments)},
                    }
                    for call in message.tool_calls
                ]
            result.append(item)
        else:
            result.append({"role": "user", "content": message.content})
    return result
