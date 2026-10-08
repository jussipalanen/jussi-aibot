"""
Provider adapters: message conversion and response parsing, without network calls.
"""
import json
from types import SimpleNamespace
from typing import Any

import httpx
import pytest
from google.genai import types

from aibot.llm import Message, ProviderError, ProviderNotConfigured, ProviderRegistry, ToolCall, ToolSpec
from aibot.llm.gemini import GeminiProvider
from aibot.llm.openai_compat import OpenAICompatProvider

pytestmark = pytest.mark.anyio

SEARCH = ToolSpec("search", "Search", {"type": "object", "properties": {"q": {"type": "string"}}})


class FakeGeminiModels:
    def __init__(self, responses: list[Any]) -> None:
        self.responses = responses
        self.requests: list[dict[str, Any]] = []

    async def generate_content(self, **kwargs: Any) -> Any:
        self.requests.append(kwargs)
        return self.responses.pop(0)

    async def embed_content(self, **kwargs: Any) -> Any:
        self.requests.append(kwargs)
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
