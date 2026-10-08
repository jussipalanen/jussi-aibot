"""
Agent loop, HTTP tools, RAG ranking and context sources, with a fake model and a mock backend.
"""
import json
from typing import Any

import httpx
import pytest

from aibot.agents.config import AgentConfig
from aibot.agents.engine import FALLBACK_REPLY, Agent, AgentUnavailable, ChatTurn
from aibot.knowledge.rag import Ranker
from aibot.llm import LLMResponse, ProviderRegistry, ToolCall
from tests.conftest import FakeProvider

pytestmark = pytest.mark.anyio

API = "https://backend.test/api"

PROPERTIES = [
    {"id": 1, "title": "Helsinki loft", "city": "Helsinki", "type": "apartment", "description": "Balcony"},
    {"id": 2, "title": "Helsinki studio", "city": "Helsinki", "type": "apartment", "description": "Sauna"},
    {"id": 3, "title": "Tampere office", "city": "Tampere", "type": "office", "description": "Office space"},
    {"id": 4, "title": "Tampere flat", "city": "Tampere", "type": "apartment", "description": "Sauna and balcony"},
]


def agent_config(**overrides: Any) -> AgentConfig:
    data: dict[str, Any] = {
        "id": "test-agent",
        "name": "Test",
        "provider": "fake",
        "system_prompt": "You help with properties.",
        "language_instructions": {"fi": "Vastaa suomeksi."},
        "auth": {
            "backend": {
                "type": "login",
                "login_url": f"{API}/auth/login",
                "body": {"email": "agent@test", "password": "secret"},
            },
        },
        "tools": [
            {
                "name": "search_properties",
                "description": "Search properties",
                "parameters": {"type": "object", "properties": {"city": {"type": "string"}, "type": {"type": "string"}}},
                "http": {"url": f"{API}/properties", "paginate": {"page_size": 2}},
                "rag": {"top_k": 1, "fields": ["title", "city", "type", "description"]},
            },
            {
                "name": "get_order_status",
                "description": "Get an order",
                "parameters": {"type": "object", "properties": {"id": {"type": "string"}}, "required": ["id"]},
                "http": {"url": f"{API}/orders/{{id}}", "auth": "backend"},
            },
        ],
    }
    data.update(overrides)
    return AgentConfig.model_validate(data)


class Backend:
    """A mock JussiSpace-like API that records requests."""

    def __init__(self) -> None:
        self.requests: list[httpx.Request] = []
        self.logins = 0
        self.valid_token = "token-1"

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        path = request.url.path
        if path == "/api/auth/login":
            self.logins += 1
            return httpx.Response(200, json={"token": f"token-{self.logins}"})
        if path == "/api/properties":
            city = request.url.params.get("city")
            items = [p for p in PROPERTIES if not city or p["city"] == city]
            page = int(request.url.params.get("page", 1))
            size = int(request.url.params.get("limit", 50))
            pages = max(1, -(-len(items) // size))
            return httpx.Response(200, json={"data": items[(page - 1) * size:page * size], "totalPages": pages})
        if path.startswith("/api/orders/"):
            if request.headers.get("authorization") != f"Bearer {self.valid_token}":
                return httpx.Response(401, json={"error": "unauthorized"})
            return httpx.Response(200, json={"id": path.rsplit("/", 1)[-1], "status": "approved"})
        return httpx.Response(404, json={"error": "not found"})


def make_agent(provider: FakeProvider, backend: Backend, config: AgentConfig | None = None) -> Agent:
    registry = ProviderRegistry()
    registry.register("fake", provider)
    http = httpx.AsyncClient(transport=httpx.MockTransport(backend.handler))
    return Agent(config or agent_config(), registry, lambda: http, Ranker())


def tool_call(name: str, **arguments: Any) -> LLMResponse:
    return LLMResponse(text="", tool_calls=[ToolCall(id=f"call-{name}", name=name, arguments=arguments)])


def tool_result(provider: FakeProvider, call_index: int) -> Any:
    """The JSON tool result the model saw in a given generate() call."""
    message = provider.calls[call_index]["messages"][-1]
    assert message.role == "tool"
    return json.loads(message.content)


async def test_answers_without_tools() -> None:
    provider = FakeProvider([LLMResponse(text="Hello!")])
    agent = make_agent(provider, Backend())
    assert await agent.chat("hi") == "Hello!"
    call = provider.calls[0]
    assert [t.name for t in call["tools"]] == ["search_properties", "get_order_status"]
    assert "You help with properties." in call["system"]


async def test_language_instruction_and_default() -> None:
    provider = FakeProvider()
    agent = make_agent(provider, Backend())
    await agent.chat("moi", language="fi")
    await agent.chat("hello", language="xx")
    assert "Vastaa suomeksi." in provider.calls[0]["system"]
    assert "same language the user writes in" in provider.calls[1]["system"]


async def test_history_is_trimmed_and_mapped() -> None:
    provider = FakeProvider()
    agent = make_agent(provider, Backend(), agent_config(history_limit=2))
    history = [ChatTurn("user", "a"), ChatTurn("assistant", "b"), ChatTurn("user", "c"), ChatTurn("bot", "d")]
    await agent.chat("e", history=history)
    messages = provider.calls[0]["messages"]
    assert [(m.role, m.content) for m in messages] == [("user", "c"), ("user", "d"), ("user", "e")]


async def test_tool_call_loop_with_pagination_and_rag() -> None:
    provider = FakeProvider([tool_call("search_properties"), LLMResponse(text="Found one.")])
    backend = Backend()
    agent = make_agent(provider, backend)

    assert await agent.chat("apartment with sauna in Tampere") == "Found one."

    # All pages fetched (4 items, page size 2), then ranked down to top_k=1.
    property_requests = [r for r in backend.requests if r.url.path == "/api/properties"]
    assert len(property_requests) == 2
    result = tool_result(provider, 1)
    assert [p["id"] for p in result["data"]] == [4]


async def test_rag_ranks_each_search_separately() -> None:
    """Regression: a cached index from one search must not answer a different search."""
    provider = FakeProvider([
        tool_call("search_properties", city="Helsinki"), LLMResponse(text="Helsinki results"),
        tool_call("search_properties", city="Tampere"), LLMResponse(text="Tampere results"),
    ])
    agent = make_agent(provider, Backend())

    await agent.chat("Helsinki apartment with sauna")
    await agent.chat("Tampere office")

    assert tool_result(provider, 1)["data"][0]["city"] == "Helsinki"
    assert tool_result(provider, 3)["data"][0]["id"] == 3


async def test_rag_reuses_cached_document_embeddings() -> None:
    provider = FakeProvider([
        tool_call("search_properties"), LLMResponse(text="1"),
        tool_call("search_properties"), LLMResponse(text="2"),
    ])
    agent = make_agent(provider, Backend())
    await agent.chat("sauna")
    await agent.chat("office")
    document_calls = [texts for texts, task in provider.embed_calls if task == "document"]
    assert len(document_calls) == 1
    assert len(document_calls[0]) == len(PROPERTIES)


async def test_undeclared_arguments_are_dropped_and_path_is_encoded() -> None:
    provider = FakeProvider([tool_call("get_order_status", id="../admin?x=1", evil="1"), LLMResponse(text="ok")])
    backend = Backend()
    agent = make_agent(provider, backend)
    await agent.chat("order")
    order_request = next(r for r in backend.requests if "/orders/" in r.url.raw_path.decode())
    assert order_request.url.raw_path.decode() == "/api/orders/..%2Fadmin%3Fx%3D1"
    assert "evil" not in str(order_request.url)


async def test_missing_path_argument_is_reported_to_model() -> None:
    provider = FakeProvider([tool_call("get_order_status"), LLMResponse(text="ok")])
    agent = make_agent(provider, Backend())
    await agent.chat("order")
    assert "missing required argument" in tool_result(provider, 1)["error"]


async def test_login_token_is_refreshed_after_401() -> None:
    provider = FakeProvider([
        tool_call("get_order_status", id="42"), LLMResponse(text="first"),
        tool_call("get_order_status", id="43"), LLMResponse(text="second"),
    ])
    backend = Backend()
    agent = make_agent(provider, backend)

    await agent.chat("order 42")
    assert tool_result(provider, 1)["status"] == "approved"
    assert backend.logins == 1

    backend.valid_token = "token-2"  # the old token expires
    await agent.chat("order 43")
    assert tool_result(provider, 3)["status"] == "approved"
    assert backend.logins == 2


async def test_unknown_tool_and_max_steps() -> None:
    provider = FakeProvider([tool_call("nope")] * 3)
    agent = make_agent(provider, Backend(), agent_config(max_steps=3))
    assert await agent.chat("loop") == FALLBACK_REPLY
    assert "unknown tool" in tool_result(provider, 1)["error"]


async def test_provider_without_tool_support_is_unavailable() -> None:
    agent = make_agent(FakeProvider(supports_tools=False), Backend())
    with pytest.raises(AgentUnavailable):
        await agent.chat("hi")


async def test_context_source_is_rendered_and_cached() -> None:
    cv = {"full_name": "Test Person", "photo": "img/me.jpg", "id": 7, "skills": [{"name": "Python"}]}
    fetches = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal fetches
        fetches += 1
        return httpx.Response(200, json=cv)

    config = AgentConfig.model_validate({
        "id": "cv", "name": "CV", "provider": "fake", "system_prompt": "About the CV.",
        "context": [{
            "name": "cv", "title": "CV DATA", "url": "https://cv.test/current", "ttl": 300,
            "asset_base_url": "https://cdn.test/", "asset_fields": ["photo"], "exclude": ["id"],
        }],
    })
    provider = FakeProvider()
    registry = ProviderRegistry()
    registry.register("fake", provider)
    http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    agent = Agent(config, registry, lambda: http, Ranker())

    await agent.chat("who?")
    await agent.chat("skills?")
    system = provider.calls[0]["system"]
    assert "CV DATA:" in system
    assert "Full name: Test Person" in system
    assert "Photo: https://cdn.test/img/me.jpg" in system
    assert "Id:" not in system
    assert "Python" in system
    assert fetches == 1
