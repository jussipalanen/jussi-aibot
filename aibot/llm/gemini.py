"""
Google Gemini provider (google-genai SDK).

Authentication, in order of preference:
- `GEMINI_API_KEY` (or `GOOGLE_API_KEY`): Gemini API key from Google AI Studio.
  Works on any host, including Render.
- `GCP_PROJECT`: Vertex AI with Application Default Credentials — the attached
  service account on Cloud Run, or `GOOGLE_APPLICATION_CREDENTIALS` elsewhere.
"""
import asyncio
import logging
import time
from collections.abc import Awaitable, Callable
from typing import Any, TypeVar

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
from aibot.settings import env, env_float, env_int

logger = logging.getLogger(__name__)

# Prefix for tool call ids we generate when the API does not return one.
_LOCAL_ID_PREFIX = "gemini-call-"
_EMBED_CONCURRENCY = 8
# Temporary server-side failures, e.g. 503 "This model is currently experiencing high demand".
# Request errors (4xx) are not retried: waiting a moment would not fix them.
_RETRY_STATUS_CODES = frozenset({500, 503, 504})
# Quota (429) is per model, so it is retried only when the next attempt uses another model.
_QUOTA_STATUS = 429

T = TypeVar("T")


def _status(exc: Exception) -> int | None:
    code = getattr(exc, "code", None)
    return code if isinstance(code, int) else None


def _is_transient(exc: Exception, *, switching_model: bool = False) -> bool:
    """True for a timeout or a google-genai API error that another attempt may fix."""
    if isinstance(exc, TimeoutError):
        return True
    code = _status(exc)
    return code in _RETRY_STATUS_CODES or (switching_model and code == _QUOTA_STATUS)


def _reason(exc: Exception) -> str:
    return "timed out" if isinstance(exc, TimeoutError) else f"failed with HTTP {_status(exc)}"


class GeminiProvider(LLMProvider):
    """Chat and embeddings through the Gemini API or Vertex AI."""

    name = "gemini"

    def __init__(
        self,
        *,
        api_key: str = "",
        project: str = "",
        location: str = "europe-north1",
        default_model: str = "gemini-3.5-flash-lite",
        embedding_model: str = "gemini-embedding-001",
        embed_batch_size: int | None = None,
        retries: int = 1,
        retry_delay: float = 2.0,
        timeout: float = 15.0,
        fallback_model: str = "",
    ) -> None:
        self.api_key = api_key
        self.project = project
        self.location = location
        self.default_model = default_model
        self.embedding_model = embedding_model
        self._embed_batch_size = embed_batch_size
        self.retries = max(0, retries)
        self.retry_delay = retry_delay
        # Seconds per attempt; 0 means no limit. The SDK has none, and Gemini sometimes takes a minute.
        self.timeout = max(0.0, timeout)
        # Chat model for retries; it has its own capacity and quota. Empty: retry the same model.
        self.fallback_model = fallback_model
        self._client: Any = None

    @classmethod
    def from_env(cls) -> "GeminiProvider":
        """Build the provider from environment variables."""
        batch_size = env_int("GEMINI_EMBED_BATCH_SIZE", 0)
        return cls(
            api_key=env("GEMINI_API_KEY", env("GOOGLE_API_KEY")),
            project=env("GCP_PROJECT"),
            location=env("GCP_LOCATION", env("AGENT_GCP_LOCATION", "europe-north1")),
            default_model=env("GEMINI_MODEL", env("VERTEX_MODEL", "gemini-3.5-flash-lite")),
            embedding_model=env("GEMINI_EMBEDDING_MODEL", "gemini-embedding-001"),
            embed_batch_size=batch_size or None,
            retries=env_int("GEMINI_RETRIES", 1),
            timeout=env_float("GEMINI_TIMEOUT", 15.0),
            fallback_model=env("GEMINI_FALLBACK_MODEL"),
        )

    @property
    def uses_vertex(self) -> bool:
        """True when requests go to Vertex AI instead of the Gemini API."""
        return not self.api_key and bool(self.project)

    def is_configured(self) -> bool:
        return bool(self.api_key or self.project)

    @property
    def embed_batch_size(self) -> int:
        """Texts per embedding request."""
        if self._embed_batch_size:
            return self._embed_batch_size
        # Vertex AI accepts one text per request for Gemini embedding models.
        if self.uses_vertex and "gemini" in self.embedding_model:
            return 1
        return 100

    def _get_client(self) -> Any:
        """Create the SDK client on first use."""
        if not self.is_configured():
            raise ProviderNotConfigured(
                "Gemini is not configured. Set GEMINI_API_KEY (Google AI Studio) "
                "or GCP_PROJECT (Vertex AI)."
            )
        if self._client is None:
            from google import genai

            if self.api_key:
                self._client = genai.Client(api_key=self.api_key)
            else:
                self._client = genai.Client(vertexai=True, project=self.project, location=self.location)
        return self._client

    async def _with_retry(self, call: Callable[[str], Awaitable[T]], model: str, *, fallback: str = "") -> T:
        """Run an API call with a time limit, retrying timeouts and temporary server errors.

        Retries use `fallback` when it names another model, straight away; otherwise the same model
        after a growing pause. Logs name the model and timing only, never the request content.
        """
        current = model
        for attempt in range(self.retries + 1):
            started = time.monotonic()
            try:
                pending = call(current)
                result = await (asyncio.wait_for(pending, self.timeout) if self.timeout else pending)
            except Exception as exc:
                elapsed = (time.monotonic() - started) * 1000
                following = fallback or current
                switching = following != current
                if attempt >= self.retries or not _is_transient(exc, switching_model=switching):
                    logger.info("Gemini %s %s after %d ms", current, _reason(exc), elapsed)
                    raise
                delay = 0.0 if switching else self.retry_delay * (attempt + 1)
                logger.info(
                    "Gemini %s %s after %d ms, retrying with %s in %.1f s",
                    current, _reason(exc), elapsed, following, delay,
                )
                current = following
                if delay:
                    await asyncio.sleep(delay)
                continue
            logger.info("Gemini %s answered in %d ms", current, (time.monotonic() - started) * 1000)
            return result
        raise AssertionError("unreachable")

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
        from google.genai import types

        client = self._get_client()
        config_args: dict[str, Any] = {}
        if system:
            config_args["system_instruction"] = system
        if temperature is not None:
            config_args["temperature"] = temperature
        if json_output and not tools:
            config_args["response_mime_type"] = "application/json"
        if tools:
            config_args["tools"] = [types.Tool(function_declarations=[
                types.FunctionDeclaration(
                    name=tool.name,
                    description=tool.description,
                    parameters_json_schema=tool.parameters,
                )
                for tool in tools
            ])]

        try:
            contents = _to_contents(messages)
            config = types.GenerateContentConfig(**config_args)
            response = await self._with_retry(lambda name: client.aio.models.generate_content(
                model=name,
                contents=contents,
                config=config,
            ), model or self.default_model, fallback=self.fallback_model)
        except ProviderNotConfigured:
            raise
        except Exception as exc:
            # Details stay in the log: they can name the project, model or quota.
            logger.warning("Gemini request failed: %s", exc)
            raise ProviderError("Gemini request failed.") from exc

        if not response.candidates or response.candidates[0].content is None:
            feedback = getattr(response, "prompt_feedback", None)
            reason = getattr(feedback, "block_reason", None) if feedback else None
            raise ProviderError(f"Gemini returned no answer{f' (blocked: {reason})' if reason else ''}.")

        content = response.candidates[0].content
        text_parts: list[str] = []
        tool_calls: list[ToolCall] = []
        for index, part in enumerate(content.parts or []):
            if part.function_call is not None:
                call = part.function_call
                tool_calls.append(ToolCall(
                    id=call.id or f"{_LOCAL_ID_PREFIX}{index}",
                    name=call.name or "",
                    arguments=dict(call.args or {}),
                ))
            elif part.text and not part.thought:
                text_parts.append(part.text)

        return LLMResponse(text="".join(text_parts).strip(), tool_calls=tool_calls, raw_message=content)

    async def embed(
        self,
        texts: list[str],
        *,
        model: str | None = None,
        task: EmbeddingTask = "document",
    ) -> list[list[float]]:
        from google.genai import types

        if not texts:
            return []
        client = self._get_client()
        config = types.EmbedContentConfig(
            task_type="RETRIEVAL_QUERY" if task == "query" else "RETRIEVAL_DOCUMENT",
        )
        size = self.embed_batch_size
        batches = [texts[i:i + size] for i in range(0, len(texts), size)]
        semaphore = asyncio.Semaphore(_EMBED_CONCURRENCY)

        async def embed_batch(batch: list[str]) -> list[list[float]]:
            async with semaphore:
                # No fallback: another embedding model would put vectors in a different space.
                response = await self._with_retry(lambda name: client.aio.models.embed_content(
                    model=name,
                    contents=batch,
                    config=config,
                ), model or self.embedding_model)
            return [list(item.values or []) for item in response.embeddings or []]

        try:
            results = await asyncio.gather(*(embed_batch(batch) for batch in batches))
        except Exception as exc:
            logger.warning("Gemini embedding request failed: %s", exc)
            raise ProviderError("Gemini embedding request failed.") from exc

        vectors = [vector for batch in results for vector in batch]
        if len(vectors) != len(texts):
            raise ProviderError("Gemini returned an unexpected number of embeddings.")
        return vectors

    async def aclose(self) -> None:
        client, self._client = self._client, None
        if client is not None:
            try:
                await client.aio.aclose()
            except Exception:  # nosec B110 - best-effort cleanup at shutdown
                pass


def _to_contents(messages: list[Message]) -> list[Any]:
    """Convert neutral messages to Gemini `Content` objects."""
    from google.genai import types

    contents: list[Any] = []
    pending_responses: list[Any] = []

    def flush_responses() -> None:
        # Gemini expects all results of one tool-calling turn in a single Content.
        if pending_responses:
            contents.append(types.Content(role="user", parts=list(pending_responses)))
            pending_responses.clear()

    for message in messages:
        if message.role == "tool":
            response_id = message.tool_call_id
            if response_id and response_id.startswith(_LOCAL_ID_PREFIX):
                response_id = None
            pending_responses.append(types.Part(function_response=types.FunctionResponse(
                id=response_id,
                name=message.name or "",
                response={"result": message.content},
            )))
            continue

        flush_responses()
        if message.role == "assistant":
            # Reuse the original content so thought signatures are sent back unchanged.
            if isinstance(message.raw, types.Content):
                contents.append(message.raw)
                continue
            parts = [types.Part.from_text(text=message.content)] if message.content else []
            for call in message.tool_calls:
                parts.append(types.Part(function_call=types.FunctionCall(
                    id=None if call.id.startswith(_LOCAL_ID_PREFIX) else call.id,
                    name=call.name,
                    args=call.arguments,
                )))
            contents.append(types.Content(role="model", parts=parts))
        else:
            contents.append(types.Content(role="user", parts=[types.Part.from_text(text=message.content)]))

    flush_responses()
    return contents
