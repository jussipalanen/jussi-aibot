"""
The `/v1` endpoints, rubrics and shipped config files.
"""
from collections.abc import Callable
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from aibot.agents.registry import AgentRegistry
from aibot.configfile import substitute_env
from aibot.review.rubrics import load_rubrics
from aibot.settings import BASE_DIR
from tests.conftest import FakeProvider

_EXTRACT = "aibot.api.deps.extract_document_text"
_DOCX = ("cv.docx", b"fake", "application/vnd.openxmlformats-officedocument.wordprocessingml.document")


def test_list_agents(client: TestClient) -> None:
    agents = {a["id"]: a for a in client.get("/v1/agents").json()}
    assert {"jussispace", "jussimatic-ai-cv-chat"} <= agents.keys()
    assert agents["jussispace"]["languages"] == ["en", "fi"]


def test_chat_unknown_agent(client: TestClient) -> None:
    assert client.post("/v1/agents/nope/chat", json={"message": "hi"}).status_code == 404


def test_chat_validates_body(client: TestClient) -> None:
    assert client.post("/v1/agents/jussispace/chat", json={"message": ""}).status_code == 422
    body = {"message": "hi", "history": [{"role": "system", "content": "x"}]}
    assert client.post("/v1/agents/jussispace/chat", json=body).status_code == 422


def test_chat_with_fake_model(make_app: Callable[..., FastAPI]) -> None:
    client = TestClient(make_app(providers={"gemini": FakeProvider(text="Moikka!")}))
    response = client.post("/v1/agents/jussispace/chat", json={"message": "moi", "language": "fi"})
    assert response.status_code == 200
    assert response.json() == {"agent": "jussispace", "reply": "Moikka!"}


def test_cv_agent_without_url_returns_503(make_app: Callable[..., FastAPI], monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("JUSSIMATIC_CV_API_URL", raising=False)
    client = TestClient(make_app(providers={"gemini": FakeProvider()}), raise_server_exceptions=False)
    response = client.post("/v1/agents/jussimatic-ai-cv-chat/chat", json={"message": "who?"})
    assert response.status_code == 503
    assert "no URL" in response.json()["detail"]


def test_list_rubrics(client: TestClient) -> None:
    rubrics = {r["id"]: r for r in client.get("/v1/review/rubrics").json()}
    assert {"cv-fi", "cv-en", "cover-letter-en"} <= rubrics.keys()
    assert rubrics["cv-en"]["labels"][5] == "Excellent"


def test_review_with_rubric(make_app: Callable[..., FastAPI]) -> None:
    gemini = FakeProvider(text='{"stars": 9, "summary": "Strong CV", "strengths": ["Clear"], "weaknesses": []}')
    client = TestClient(make_app(providers={"gemini": gemini}))
    with patch(_EXTRACT, return_value="Jane Doe. Experience: 5 years."):
        response = client.post("/v1/review", data={"rubric": "cv-en"}, files={"file": _DOCX})
    assert response.status_code == 200
    data = response.json()
    assert data["stars"] == 5
    assert data["rating_text"] == "Excellent"
    assert data["rubric"] == "cv-en"
    prompt = gemini.calls[0]["messages"][0].content
    assert "Jane Doe. Experience: 5 years." in prompt
    assert "{document_text}" not in prompt


def test_review_cv_fi_falls_back_to_heuristics(make_app: Callable[..., FastAPI]) -> None:
    client = TestClient(make_app(providers={"gemini": FakeProvider(text="not json")}))
    with patch(_EXTRACT, return_value="Nimi kokemus koulutus osaaminen"):
        response = client.post("/v1/review", files={"file": _DOCX})
    assert response.status_code == 200
    assert response.json()["rubric"] == "cv-fi"


def test_review_without_json_returns_502(make_app: Callable[..., FastAPI]) -> None:
    client = TestClient(make_app(providers={"gemini": FakeProvider(text="not json")}), raise_server_exceptions=False)
    with patch(_EXTRACT, return_value="text"):
        response = client.post("/v1/review", data={"rubric": "cv-en"}, files={"file": _DOCX})
    assert response.status_code == 502


def test_review_unknown_rubric_and_provider(client: TestClient) -> None:
    assert client.post("/v1/review", data={"rubric": "nope"}, files={"file": _DOCX}).status_code == 404
    response = client.post("/v1/review", data={"provider": "nope"}, files={"file": _DOCX})
    assert response.status_code == 400


def test_review_other_provider(make_app: Callable[..., FastAPI]) -> None:
    groq = FakeProvider(text='{"stars": 3, "summary": "ok", "strengths": [], "weaknesses": []}')
    client = TestClient(make_app(providers={"groq": groq}))
    with patch(_EXTRACT, return_value="text"):
        response = client.post("/v1/review", data={"rubric": "cv-en", "provider": "groq", "model": "m1"},
                               files={"file": _DOCX})
    assert response.status_code == 200
    assert groq.calls[0]["model"] == "m1"


def test_providers_endpoint(make_app: Callable[..., FastAPI], monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GEMINI_API_KEY", "x")
    client = TestClient(make_app())
    providers = {p["name"]: p for p in client.get("/v1/providers").json()}
    assert providers["gemini"]["configured"] is True
    assert providers["puter"]["configured"] is False
    assert providers["puter"]["tools"] is False


def test_openapi_lists_v1_and_marks_legacy_deprecated(client: TestClient) -> None:
    paths = client.get("/openapi.json").json()["paths"]
    assert "/v1/agents/{agent_id}/chat" in paths
    assert paths["/ai/chat"]["post"]["deprecated"] is True


# ── Config files ───────────────────────────────────────────────────────────

def test_shipped_agents_load() -> None:
    configs = {c.id: c for c in AgentRegistry.load_configs(BASE_DIR / "config" / "agents")}
    assert {"jussispace", "jussimatic-ai-cv-chat"} <= configs.keys()
    tools = {t.name: t for t in configs["jussispace"].tools}
    assert tools["search_properties"].rag is not None
    assert tools["get_order_status"].http.auth == "jussispace"


def test_shipped_rubrics_load() -> None:
    assert {"cv-fi", "cv-en", "cover-letter-en"} <= load_rubrics(BASE_DIR / "config" / "rubrics").keys()


def test_agent_model_env_fallbacks(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("JUSSISPACE_VERTEX_MODEL", raising=False)
    monkeypatch.setenv("AGENT_VERTEX_MODEL", "gemini-x")
    configs = {c.id: c for c in AgentRegistry.load_configs(BASE_DIR / "config" / "agents")}
    assert configs["jussispace"].model == "gemini-x"
    monkeypatch.setenv("JUSSISPACE_VERTEX_MODEL", "gemini-y")
    configs = {c.id: c for c in AgentRegistry.load_configs(BASE_DIR / "config" / "agents")}
    assert configs["jussispace"].model == "gemini-y"


def test_substitute_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("A_SET", "a")
    monkeypatch.delenv("B_UNSET", raising=False)
    assert substitute_env("${A_SET}/${B_UNSET:-b}/${B_UNSET}") == "a/b/"
    assert substitute_env("${B_UNSET:-${A_SET:-c}}") == "a"
    assert substitute_env("{images[0]} $HOME") == "{images[0]} $HOME"


def test_invalid_agent_config_is_reported(tmp_path: Path) -> None:
    (tmp_path / "bad.yaml").write_text("id: bad\nname: Bad\nsystem_prompt: x\nunknown_key: 1\n", encoding="utf-8")
    with pytest.raises(ValueError, match="bad.yaml"):
        AgentRegistry.load_configs(tmp_path)
