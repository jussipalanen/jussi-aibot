"""
Client authentication, origin checks and rate limits.
"""
from collections.abc import Callable
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from aibot.security import hash_key
from tests.conftest import FakeProvider

CHAT = {"handler": "jussispace", "message": "hi"}


def _app(make_app: Callable[..., FastAPI], **env: str) -> TestClient:
    app = make_app(env=env, providers={"gemini": FakeProvider(text="hello")})
    return TestClient(app, raise_server_exceptions=False)


def _clients_file(tmp_path: Path, content: str) -> str:
    path = tmp_path / "clients.yaml"
    path.write_text(content, encoding="utf-8")
    return str(path)


# ── Legacy single-key settings ─────────────────────────────────────────────

def test_open_access_without_config(make_app: Callable[..., FastAPI]) -> None:
    client = _app(make_app)
    assert client.post("/ai/chat", json=CHAT).status_code == 200


def test_key_required_when_secret_set(make_app: Callable[..., FastAPI]) -> None:
    client = _app(make_app, AI_SECRET_KEY="s3cret")
    assert client.post("/ai/chat", json=CHAT).status_code == 401
    assert client.post("/ai/chat", json=CHAT, headers={"Authorization": "Bearer wrong"}).status_code == 401
    assert client.post("/ai/chat", json=CHAT, headers={"Authorization": "Bearer s3cret"}).status_code == 200


def test_server_call_with_key_and_no_origin_is_allowed(make_app: Callable[..., FastAPI]) -> None:
    """Regression: with both settings, server-to-server calls (no Origin) were blocked."""
    client = _app(make_app, AI_SECRET_KEY="s3cret", ALLOWED_ORIGINS="https://app.test")
    response = client.post("/ai/chat", json=CHAT, headers={"Authorization": "Bearer s3cret"})
    assert response.status_code == 200


def test_key_with_unlisted_origin_is_forbidden(make_app: Callable[..., FastAPI]) -> None:
    client = _app(make_app, AI_SECRET_KEY="s3cret", ALLOWED_ORIGINS="https://app.test")
    headers = {"Authorization": "Bearer s3cret", "Origin": "https://evil.test"}
    assert client.post("/ai/chat", json=CHAT, headers=headers).status_code == 403


def test_allowed_origin_still_needs_key_when_secret_set(make_app: Callable[..., FastAPI]) -> None:
    client = _app(make_app, AI_SECRET_KEY="s3cret", ALLOWED_ORIGINS="https://app.test")
    assert client.post("/ai/chat", json=CHAT, headers={"Origin": "https://app.test"}).status_code == 401


@pytest.mark.parametrize("origin,expected", [
    ("https://app.test", 200),
    ("https://app.test/", 200),
    ("https://evil.test", 403),
    ("https://app.test.evil.test", 403),
    ("", 401),
])
def test_origin_only_settings(make_app: Callable[..., FastAPI], origin: str, expected: int) -> None:
    client = _app(make_app, ALLOWED_ORIGINS="https://app.test")
    headers = {"Origin": origin} if origin else {}
    assert client.post("/ai/chat", json=CHAT, headers=headers).status_code == expected


# ── clients.yaml ───────────────────────────────────────────────────────────

CLIENTS = f"""
clients:
  - id: backend
    key_sha256: {hash_key("backend-key")}
    agents: [jussimatic-ai-cv-chat]
    rubrics: [cv-en]
  - id: web
    origins: [https://space.test]
    agents: [jussispace]
    rate_limit: 2/minute
"""


def test_clients_file_scopes_agents(make_app: Callable[..., FastAPI], tmp_path: Path) -> None:
    client = _app(make_app, CLIENTS_FILE=_clients_file(tmp_path, CLIENTS))
    backend = {"Authorization": "Bearer backend-key"}
    web = {"Origin": "https://space.test"}

    assert [a["id"] for a in client.get("/v1/agents", headers=backend).json()] == ["jussimatic-ai-cv-chat"]
    assert [a["id"] for a in client.get("/v1/agents", headers=web).json()] == ["jussispace"]
    assert client.post("/v1/agents/jussispace/chat", json={"message": "hi"}, headers=backend).status_code == 404
    assert client.post("/v1/agents/jussispace/chat", json={"message": "hi"}, headers=web).status_code == 200
    assert [r["id"] for r in client.get("/v1/review/rubrics", headers=backend).json()] == ["cv-en"]


def test_client_rate_limit(make_app: Callable[..., FastAPI], tmp_path: Path) -> None:
    client = _app(make_app, CLIENTS_FILE=_clients_file(tmp_path, CLIENTS))
    web = {"Origin": "https://space.test"}
    statuses = [client.post("/v1/agents/jussispace/chat", json={"message": "hi"}, headers=web).status_code
                for _ in range(3)]
    assert statuses == [200, 200, 429]
    response = client.post("/v1/agents/jussispace/chat", json={"message": "hi"}, headers=web)
    assert int(response.headers["retry-after"]) >= 1


def test_rate_limit_uses_forwarded_ip(make_app: Callable[..., FastAPI], tmp_path: Path) -> None:
    client = _app(make_app, CLIENTS_FILE=_clients_file(tmp_path, CLIENTS), FORWARDED_IP_DEPTH="1")
    web = {"Origin": "https://space.test"}

    def chat(ip: str) -> int:
        headers = {**web, "X-Forwarded-For": f"6.6.6.6, {ip}"}
        return client.post("/v1/agents/jussispace/chat", json={"message": "hi"}, headers=headers).status_code

    assert [chat("1.1.1.1") for _ in range(3)] == [200, 200, 429]
    assert chat("2.2.2.2") == 200


def test_cors_allows_configured_origins_only(make_app: Callable[..., FastAPI], tmp_path: Path) -> None:
    client = _app(make_app, CLIENTS_FILE=_clients_file(tmp_path, CLIENTS))
    preflight = {"Access-Control-Request-Method": "POST"}
    ok = client.options("/v1/agents", headers={**preflight, "Origin": "https://space.test"})
    bad = client.options("/v1/agents", headers={**preflight, "Origin": "https://evil.test"})
    assert ok.headers.get("access-control-allow-origin") == "https://space.test"
    assert "access-control-allow-origin" not in bad.headers


def test_client_key_from_env(make_app: Callable[..., FastAPI], tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MY_KEY", "from-env")
    path = _clients_file(tmp_path, "clients:\n  - id: svc\n    key: ${MY_KEY}\n")
    client = _app(make_app, CLIENTS_FILE=path)
    assert client.get("/v1/agents", headers={"Authorization": "Bearer from-env"}).status_code == 200


def test_client_without_key_or_origins_is_rejected(make_app: Callable[..., FastAPI], tmp_path: Path) -> None:
    path = _clients_file(tmp_path, "clients:\n  - id: svc\n    key: ${UNSET_KEY_FOR_TEST}\n")
    with pytest.raises(ValueError, match="needs a key"):
        make_app(env={"CLIENTS_FILE": path})


def test_invalid_rate_limit_fails_at_startup(make_app: Callable[..., FastAPI]) -> None:
    with pytest.raises(ValueError):
        make_app(env={"DAILY_RATE_LIMIT": "lots"})
