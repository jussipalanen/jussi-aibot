"""
Provider adapters: message conversion and response parsing, without network calls.
"""
import asyncio
import json
import logging
from types import SimpleNamespace
from typing import Any

import httpx
import pytest
from google.genai import errors as genai_errors
from google.genai import types

from aibot.llm import Message, ProviderError, ProviderNotConfigured, ProviderRegistry, ToolCall, ToolSpec
from aibot.llm.gemini import GeminiProvider
from aibot.llm.openai_compat import OpenAICompatProvider
from aibot.settings import configure_logging

pytestmark = pytest.mark.anyio

SEARCH = ToolSpec("search", "Search", {"type": "object", "properties": {"q": {"type": "string"}}})
# A fake response that never arrives in time, like a Gemini call stuck for a minute.
SLOW = object()
# Kept apart from asyncio.sleep, which tests replace to skip retry pauses.
_real_sleep = asyncio.sleep


class FakeGeminiModels:
    def __init__(self, responses: list[Any]) -> None:
        self.responses = responses
        self.requests: list[dict[str, Any]] = []

    async def generate_content(self, **kwargs: Any) -> Any:
        self.requests.append(kwargs)
        response = self.responses.pop(0)
        if response is SLOW:
            await _real_sleep(60)
        if isinstance(response, Exception):
            raise response
        return response

    async def embed_content(self, **kwargs: Any) -> Any:
        self.requests.append(kwargs)
        if self.responses and self.responses[0] is SLOW:
            self.responses.pop(0)
            await _real_sleep(60)
        if self.responses and isinstance(self.responses[0], Exception):
            raise self.responses.pop(0)
        return SimpleNamespace(embeddings=[SimpleNamespace(values=[float(len(t))]) for t in kwargs["contents"]])


def gemini_with(responses: list[Any], **kwargs: Any) -> tuple[GeminiProvider, FakeGeminiModels]:
    provider = GeminiProvider(api_key="key", **kwargs)
    models = FakeGeminiModels(responses)
    provider._client = SimpleNamespace(aio=SimpleNamespace(models=models))
    return provider, models


def gemini_response(*parts: types.Part) -> types.GenerateContentResponse:
    return types.GenerateContentResponse(candidates=[
        types.Candidate(content=types.Content(role="model", parts=list(parts))),
    ])


async def test_gemini_not_configured() -> None:
    provider = GeminiProvider()
    assert not provider.is_configured()
    with pytest.raises(ProviderNotConfigured, match="GEMINI_API_KEY"):
        await provider.generate([Message("user", "hi")])


def test_gemini_auth_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GCP_PROJECT", "proj")
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    vertex = GeminiProvider.from_env()
    assert vertex.uses_vertex and vertex.embed_batch_size == 1
    monkeypatch.setenv("GEMINI_API_KEY", "key")
    api = GeminiProvider.from_env()
    assert not api.uses_vertex and api.embed_batch_size == 100


async def test_gemini_text_and_tool_calls() -> None:
    call_part = types.Part(function_call=types.FunctionCall(name="search", args={"q": "sauna"}))
    thought = types.Part(text="thinking...", thought=True)
    provider, models = gemini_with([gemini_response(thought, types.Part(text="Let me look."), call_part)])

    response = await provider.generate([Message("user", "find")], system="sys", tools=[SEARCH])

    assert response.text == "Let me look."
    assert response.tool_calls == [ToolCall(id="gemini-call-2", name="search", arguments={"q": "sauna"})]
    config = models.requests[0]["config"]
    assert config.system_instruction == "sys"
    assert config.tools[0].function_declarations[0].name == "search"


async def test_gemini_sends_tool_results_back() -> None:
    first = gemini_response(types.Part(function_call=types.FunctionCall(name="search", args={})))
    provider, models = gemini_with([first, gemini_response(types.Part(text="Done"))])
    reply = await provider.generate([Message("user", "find")], tools=[SEARCH])

    history = [
        Message("user", "find"),
        Message("assistant", reply.text, tool_calls=reply.tool_calls, raw=reply.raw_message),
        Message("tool", '{"data": []}', tool_call_id=reply.tool_calls[0].id, name="search"),
    ]
    assert (await provider.generate(history, tools=[SEARCH])).text == "Done"

    contents = models.requests[1]["contents"]
    assert [c.role for c in contents] == ["user", "model", "user"]
    assert contents[1] is reply.raw_message  # original content (and thought signatures) reused
    function_response = contents[2].parts[0].function_response
    assert function_response.name == "search"
    assert function_response.id is None  # locally generated ids are not sent to the API


async def test_gemini_blocked_response() -> None:
    provider, _ = gemini_with([types.GenerateContentResponse(candidates=[])])
    with pytest.raises(ProviderError, match="no answer"):
        await provider.generate([Message("user", "hi")])


async def test_gemini_embeddings_in_batches() -> None:
    provider, models = gemini_with([], embed_batch_size=2)
    vectors = await provider.embed(["a", "bb", "ccc"], task="query")
    assert vectors == [[1.0], [2.0], [3.0]]
    assert len(models.requests) == 2
    assert models.requests[0]["config"].task_type == "RETRIEVAL_QUERY"


def api_error(code: int) -> genai_errors.APIError:
    status = {429: "RESOURCE_EXHAUSTED", 503: "UNAVAILABLE"}.get(code, "ERROR")
    error_class = genai_errors.ServerError if code >= 500 else genai_errors.ClientError
    return error_class(code, {"error": {"code": code, "message": "high demand", "status": status}})


async def test_gemini_retries_temporary_server_errors() -> None:
    provider, models = gemini_with([api_error(503), gemini_response(types.Part(text="ok"))], retry_delay=0)
    assert (await provider.generate([Message("user", "hi")])).text == "ok"
    assert len(models.requests) == 2


async def test_gemini_gives_up_after_the_retries() -> None:
    provider, models = gemini_with([api_error(503), api_error(503), api_error(503)], retries=2, retry_delay=0)
    with pytest.raises(ProviderError, match="Gemini request failed"):
        await provider.generate([Message("user", "hi")])
    assert len(models.requests) == 3


@pytest.mark.parametrize("code", [400, 429])
async def test_gemini_does_not_retry_client_or_quota_errors(code: int) -> None:
    provider, models = gemini_with([api_error(code), gemini_response(types.Part(text="ok"))], retry_delay=0)
    with pytest.raises(ProviderError):
        await provider.generate([Message("user", "hi")])
    assert len(models.requests) == 1


async def test_gemini_retry_can_be_turned_off_and_covers_embeddings(monkeypatch: pytest.MonkeyPatch) -> None:
    provider, models = gemini_with([api_error(503), gemini_response(types.Part(text="ok"))], retries=0, retry_delay=0)
    with pytest.raises(ProviderError):
        await provider.generate([Message("user", "hi")])
    assert len(models.requests) == 1

    provider, models = gemini_with([api_error(504)], retry_delay=0)
    assert await provider.embed(["a"]) == [[1.0]]
    assert len(models.requests) == 2

    monkeypatch.setenv("GEMINI_RETRIES", "3")
    assert GeminiProvider.from_env().retries == 3


async def test_gemini_times_out_a_stuck_call_and_retries_with_the_fallback_model(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pauses: list[float] = []

    async def no_pause(delay: float) -> None:
        pauses.append(delay)

    provider, models = gemini_with(
        [SLOW, gemini_response(types.Part(text="ok"))], timeout=0.05, fallback_model="backup", retry_delay=30,
    )
    monkeypatch.setattr("aibot.llm.gemini.asyncio.sleep", no_pause)
    assert (await provider.generate([Message("user", "hi")])).text == "ok"
    assert [r["model"] for r in models.requests] == ["gemini-3.5-flash-lite", "backup"]
    assert pauses == []  # another model has its own capacity, so no reason to wait


async def test_gemini_retries_the_same_model_after_a_pause_without_a_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    pauses: list[float] = []

    async def no_pause(delay: float) -> None:
        pauses.append(delay)

    provider, models = gemini_with([api_error(503), gemini_response(types.Part(text="ok"))], retry_delay=2)
    monkeypatch.setattr("aibot.llm.gemini.asyncio.sleep", no_pause)
    assert (await provider.generate([Message("user", "hi")], model="custom")).text == "ok"
    assert [r["model"] for r in models.requests] == ["custom", "custom"]
    assert pauses == [2]


async def test_gemini_gives_up_when_every_attempt_times_out() -> None:
    provider, models = gemini_with([SLOW, SLOW], timeout=0.05, fallback_model="backup")
    with pytest.raises(ProviderError, match="Gemini request failed"):
        await provider.generate([Message("user", "hi")])
    assert len(models.requests) == 2


async def test_gemini_quota_error_is_retried_only_with_another_model() -> None:
    provider, models = gemini_with([api_error(429), gemini_response(types.Part(text="ok"))], fallback_model="backup", retry_delay=0)
    assert (await provider.generate([Message("user", "hi")])).text == "ok"
    assert [r["model"] for r in models.requests] == ["gemini-3.5-flash-lite", "backup"]

    # The fallback is the model already in use: the same quota, so no retry.
    provider, models = gemini_with([api_error(429), gemini_response(types.Part(text="ok"))], fallback_model="backup", retry_delay=0)
    with pytest.raises(ProviderError):
        await provider.generate([Message("user", "hi")], model="backup")
    assert len(models.requests) == 1


async def test_gemini_embeddings_time_out_but_never_switch_model() -> None:
    provider, models = gemini_with([SLOW], timeout=0.05, fallback_model="backup", retry_delay=0)
    assert await provider.embed(["a"]) == [[1.0]]
    assert [r["model"] for r in models.requests] == ["gemini-embedding-001", "gemini-embedding-001"]


async def test_gemini_timeout_zero_means_no_limit() -> None:
    provider, _ = gemini_with([gemini_response(types.Part(text="ok"))], timeout=0)
    assert provider.timeout == 0
    assert (await provider.generate([Message("user", "hi")])).text == "ok"


def test_gemini_timeout_and_fallback_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("GEMINI_TIMEOUT", raising=False)
    monkeypatch.delenv("GEMINI_FALLBACK_MODEL", raising=False)
    default = GeminiProvider.from_env()
    assert (default.timeout, default.fallback_model) == (15.0, "")
    monkeypatch.setenv("GEMINI_TIMEOUT", "7.5")
    monkeypatch.setenv("GEMINI_FALLBACK_MODEL", "gemini-3.5-flash")
    configured = GeminiProvider.from_env()
    assert (configured.timeout, configured.fallback_model) == (7.5, "gemini-3.5-flash")


async def test_gemini_logs_model_and_timing_but_not_the_request(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.INFO, logger="aibot.llm.gemini")
    provider, _ = gemini_with([api_error(503), gemini_response(types.Part(text="ok"))], fallback_model="backup", retry_delay=0)
    await provider.generate([Message("user", "secret question")], system="secret prompt")
    text = caplog.text
    assert "gemini-3.5-flash-lite failed with HTTP 503 after" in text
    assert "retrying with backup in 0.0 s" in text
    assert "Gemini backup answered in" in text
    assert "secret" not in text


def test_configure_logging_shows_app_info_logs_once(monkeypatch: pytest.MonkeyPatch) -> None:
    logger = logging.getLogger("aibot")
    saved = (logger.handlers[:], logger.level, logger.propagate)
    logger.handlers.clear()
    try:
        monkeypatch.setenv("LOG_LEVEL", "warning")
        configure_logging()
        configure_logging()  # a second call adds nothing
        assert len(logger.handlers) == 1
        assert logger.level == logging.WARNING and not logger.propagate
        monkeypatch.delenv("LOG_LEVEL")
        logger.handlers.clear()
        configure_logging()
        assert logger.level == logging.INFO
    finally:
        logger.handlers[:], logger.level, logger.propagate = saved  # type: ignore[assignment]
        logger.setLevel(saved[1])


def openai_provider(handler: Any, **kwargs: Any) -> OpenAICompatProvider:
    return OpenAICompatProvider(
        "groq", base_url="https://llm.test/v1", api_key="k", default_model="m",
        transport=httpx.MockTransport(handler), **kwargs,
    )


async def test_openai_compat_tool_round_trip() -> None:
    seen: list[dict[str, Any]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        seen.append(body)
        assert request.headers["authorization"] == "Bearer k"
        if len(seen) == 1:
            return httpx.Response(200, json={"choices": [{"message": {"content": None, "tool_calls": [
                {"id": "c1", "type": "function", "function": {"name": "search", "arguments": '{"q": "x"}'}},
            ]}}]})
        return httpx.Response(200, json={"choices": [{"message": {"content": "Answer"}}]})

    provider = openai_provider(handler)
    first = await provider.generate([Message("user", "hi")], system="sys", tools=[SEARCH])
    assert first.tool_calls == [ToolCall(id="c1", name="search", arguments={"q": "x"})]

    history = [
        Message("user", "hi"),
        Message("assistant", "", tool_calls=first.tool_calls),
        Message("tool", "[]", tool_call_id="c1", name="search"),
    ]
    assert (await provider.generate(history, tools=[SEARCH])).text == "Answer"

    assert seen[0]["messages"][0] == {"role": "system", "content": "sys"}
    assert seen[0]["tools"][0]["function"]["name"] == "search"
    assert seen[1]["messages"][1]["tool_calls"][0]["function"]["arguments"] == '{"q": "x"}'
    assert seen[1]["messages"][2] == {"role": "tool", "tool_call_id": "c1", "content": "[]"}


async def test_openai_compat_errors() -> None:
    provider = openai_provider(lambda request: httpx.Response(429, text="slow down"))
    with pytest.raises(ProviderError, match="429"):
        await provider.generate([Message("user", "hi")])


async def test_openai_compat_needs_key_and_model() -> None:
    with pytest.raises(ProviderNotConfigured, match="GROQ_API_KEY"):
        await OpenAICompatProvider("groq", base_url="https://x").generate([Message("user", "hi")])
    provider = openai_provider(lambda request: httpx.Response(200, json={}))
    provider.default_model = ""
    with pytest.raises(ProviderNotConfigured, match="GROQ_MODEL"):
        await provider.generate([Message("user", "hi")])


def test_registry_aliases() -> None:
    registry = ProviderRegistry()
    assert registry.get("vertex_ai") is registry.get("gemini")
    assert registry.get("puter_ai").name == "puter"
    assert registry.exists("default")
    with pytest.raises(ProviderNotConfigured):
        registry.get("nope")
