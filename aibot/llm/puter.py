"""
Puter AI provider (text generation only — no tool calling or embeddings).
"""
import json

from starlette.concurrency import run_in_threadpool

from aibot.llm.base import (
    LLMProvider,
    LLMResponse,
    Message,
    ProviderError,
    ProviderNotConfigured,
    ToolSpec,
)
from aibot.settings import env


class PuterProvider(LLMProvider):
    """Chat completions through the Puter SDK."""

    name = "puter"
    supports_tools = False
    supports_embeddings = False

    def __init__(self, *, api_key: str = "", default_model: str = "gpt-4o-mini", driver: str = "openai-completion") -> None:
        self.api_key = api_key
        self.default_model = default_model
        self.driver = driver

    @classmethod
    def from_env(cls) -> "PuterProvider":
        """Build the provider from environment variables."""
        return cls(
            api_key=env("PUTER_API_KEY"),
            default_model=env("PUTER_MODEL", "gpt-4o-mini"),
            driver=env("PUTER_DRIVER", "openai-completion"),
        )

    def is_configured(self) -> bool:
        return bool(self.api_key)

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
        if not self.api_key:
            raise ProviderNotConfigured("Puter AI is not configured. Missing PUTER_API_KEY.")
        if tools:
            raise ProviderNotConfigured("Puter AI does not support tool calling.")

        try:
            from puter import ChatCompletion
        except ImportError as exc:
            raise ProviderNotConfigured("Puter AI SDK is not installed.") from exc

        payload = [{"role": "system", "content": system}] if system else []
        payload += [
            {"role": "assistant" if m.role == "assistant" else "user", "content": m.content}
            for m in messages
        ]
        try:
            response = await run_in_threadpool(
                ChatCompletion.create,
                messages=payload,
                model=model or self.default_model,
                driver=self.driver,
                api_key=self.api_key,
            )
        except Exception as exc:
            raise ProviderError(f"Puter AI request failed: {exc}") from exc

        return LLMResponse(text=extract_puter_text(response))


def extract_puter_text(response: object) -> str:
    """Extract text from the Puter response shapes seen in practice."""
    if isinstance(response, str):
        return response.strip()

    if isinstance(response, dict):
        # Common SDK shape: {"success": true, "result": {"message": {"content": "..."}}}
        result = response.get("result")
        if isinstance(result, dict):
            message = result.get("message")
            if isinstance(message, dict) and isinstance(message.get("content"), str):
                return message["content"].strip()

        # Surface explicit provider error payloads when present.
        if response.get("success") is False or ("error" in response and "status" in response):
            error_msg = response.get("error") or response.get("message")
            if isinstance(error_msg, str) and error_msg.strip():
                raise ProviderError(f"Puter AI request failed: {error_msg.strip()}")

        choices = response.get("choices")
        if isinstance(choices, list) and choices and isinstance(choices[0], dict):
            first = choices[0]
            message = first.get("message")
            if isinstance(message, dict) and isinstance(message.get("content"), str):
                return message["content"].strip()
            if isinstance(first.get("text"), str):
                return first["text"].strip()

        message = response.get("message")
        if isinstance(message, dict) and isinstance(message.get("content"), str):
            return message["content"].strip()
        if isinstance(response.get("content"), str):
            return response["content"].strip()

    choices = getattr(response, "choices", None)
    if isinstance(choices, list) and choices:
        first = choices[0]
        message = getattr(first, "message", None)
        content = getattr(message, "content", None) if message is not None else None
        if isinstance(content, str):
            return content.strip()
        text = getattr(first, "text", None)
        if isinstance(text, str):
            return text.strip()

    content = getattr(response, "content", None)
    if isinstance(content, str):
        return content.strip()

    try:
        response_debug = json.dumps(response, default=str)
    except (TypeError, ValueError):
        response_debug = str(response)
    raise ProviderError(
        f"Puter AI returned an unreadable response. Response structure: {response_debug[:500]}"
    )

