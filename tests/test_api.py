"""
Tests for the service pages and the legacy `/ai/chat` and `/ai/review` endpoints.
"""
from collections.abc import Callable
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from tests.conftest import FakeProvider

_MOCK_REVIEW_JSON = (
    '{"stars": 4, "rating_text": "Erittäin hyvä", '
    '"summary": "Hyvä CV", "strengths": ["Kokemus"], "weaknesses": ["Lyhyt"]}'
)

_MINIMAL_PDF = (
    b"%PDF-1.4\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n"
    b"2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj\n"
    b"3 0 obj<</Type/Page/MediaBox[0 0 612 792]/Parent 2 0 R>>endobj\n"
    b"xref\n0 4\ntrailer<</Size 4/Root 1 0 R>>\nstartxref\n0\n%%EOF"
)

_EXTRACT = "aibot.api.deps.extract_document_text"


class FakeAgent:
    """Stands in for an agent and records the call."""

    def __init__(self, reply: str = "", error: Exception | None = None) -> None:
        self.reply = reply
        self.error = error
        self.calls: list[tuple] = []

    async def chat(self, message, language=None, history=None):
        self.calls.append((message, language, history))
        if self.error:
            raise self.error
        return self.reply


def _with_agent(app: FastAPI, agent: FakeAgent) -> TestClient:
    app.state.services.agents.get = lambda agent_id: agent
    return TestClient(app, raise_server_exceptions=False)


# ── Service pages ──────────────────────────────────────────────────────────

def test_root_html_links_to_docs(client: TestClient) -> None:
    response = client.get("/", headers={"accept": "text/html"})
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert 'href="/docs"' in response.text
    assert "Jussi AI Bot" in response.text


def test_root_json(client: TestClient) -> None:
    response = client.get("/", headers={"accept": "application/json"})
    assert response.status_code == 200
    assert response.json()["docs"] == "/docs"


def test_root_escapes_app_name(make_app: Callable[..., FastAPI]) -> None:
    client = TestClient(make_app(env={"APP_NAME": "<script>x</script>"}))
    assert "<script>x</script>" not in client.get("/").text


def test_health(client: TestClient) -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_health_head(client: TestClient) -> None:
    """Uptime monitors such as UptimeRobot send HEAD by default."""
    response = client.head("/health")
    assert response.status_code == 200
    assert response.content == b""


def test_version(client: TestClient) -> None:
    data = client.get("/version").json()
    assert "python_version" in data
    assert "fastapi_version" in data
    assert data["version"]


def test_docs_available(client: TestClient) -> None:
    assert client.get("/docs").status_code == 200
    assert client.get("/openapi.json").status_code == 200


def test_robots_txt(client: TestClient) -> None:
    response = client.get("/robots.txt")
    assert response.status_code == 200
    assert "Disallow" in response.text


def test_robots_header_present(client: TestClient) -> None:
    response = client.get("/health")
    assert "noindex" in response.headers.get("x-robots-tag", "")


# ── /ai/review — input validation ─────────────────────────────────────────

def test_review_missing_file(client: TestClient) -> None:
    assert client.post("/ai/review").status_code == 422


def test_review_unsupported_extension(client: TestClient) -> None:
    response = client.post("/ai/review", files={"file": ("resume.txt", b"some content", "text/plain")})
    assert response.status_code == 400
    assert "Unsupported file type" in response.json()["detail"]


def test_review_empty_filename(client: TestClient) -> None:
    response = client.post("/ai/review", files={"file": ("", b"content", "application/octet-stream")})
    assert response.status_code in (400, 422)


def test_review_invalid_provider(client: TestClient) -> None:
    response = client.post(
        "/ai/review",
        data={"provider": "nonexistent_provider"},
        files={"file": ("resume.pdf", b"%PDF fake", "application/pdf")},
    )
    assert response.status_code == 400
    assert "provider" in response.json()["detail"].lower()


def test_review_unreadable_pdf_returns_400(client: TestClient) -> None:
    response = client.post(
        "/ai/review",
        data={"provider": "puter_ai"},
        files={"file": ("resume.pdf", b"not a pdf", "application/pdf")},
    )
    assert response.status_code == 400


# ── /ai/review — provider flows ───────────────────────────────────────────

def test_review_puter_ai_success(make_app: Callable[..., FastAPI]) -> None:
    client = TestClient(make_app(providers={"puter": FakeProvider(text=_MOCK_REVIEW_JSON)}))
    with patch(_EXTRACT, return_value="Nimi Matti Meikäläinen kokemus koulutus osaaminen"):
        response = client.post(
            "/ai/review",
            data={"provider": "puter_ai"},
            files={"file": ("resume.pdf", _MINIMAL_PDF, "application/pdf")},
        )
    assert response.status_code == 200
    data = response.json()
    assert data["stars"] == 4
    assert isinstance(data["strengths"], list)


def test_review_vertex_ai_uses_gemini(make_app: Callable[..., FastAPI]) -> None:
    gemini = FakeProvider(text=_MOCK_REVIEW_JSON)
    client = TestClient(make_app(providers={"gemini": gemini}))
    with patch(_EXTRACT, return_value="Nimi Matti kokemus koulutus osaaminen"):
        response = client.post(
            "/ai/review",
            data={"provider": "vertex_ai"},
            files={"file": ("resume.docx", b"fake docx", "application/vnd.openxmlformats-officedocument.wordprocessingml.document")},
        )
    assert response.status_code == 200
    assert gemini.calls[0]["json_output"] is True
    assert "Arviointikriteerit" in gemini.calls[0]["messages"][0].content


def test_review_puter_ai_missing_key(client: TestClient) -> None:
    """Without PUTER_API_KEY the service should return 503."""
    with patch(_EXTRACT, return_value="some text"):
        response = client.post(
            "/ai/review",
            data={"provider": "puter_ai"},
            files={"file": ("resume.pdf", _MINIMAL_PDF, "application/pdf")},
        )
    assert response.status_code == 503


def test_review_gemini_missing_credentials(client: TestClient) -> None:
    with patch(_EXTRACT, return_value="some text"):
        response = client.post(
            "/ai/review",
            data={"provider": "vertex_ai"},
            files={"file": ("resume.pdf", _MINIMAL_PDF, "application/pdf")},
        )
    assert response.status_code == 503
    assert "GEMINI_API_KEY" in response.json()["detail"]


def test_review_response_shape(make_app: Callable[..., FastAPI]) -> None:
    client = TestClient(make_app(providers={"puter": FakeProvider(text=_MOCK_REVIEW_JSON)}))
    with patch(_EXTRACT, return_value="Nimi kokemus koulutus osaaminen"):
        response = client.post(
            "/ai/review",
            data={"provider": "puter_ai"},
            files={"file": ("resume.pdf", _MINIMAL_PDF, "application/pdf")},
        )
    assert response.status_code == 200
    for key in ("stars", "rating_text", "summary", "strengths", "weaknesses", "provider_raw_output"):
        assert key in response.json(), f"Missing key: {key}"


# ── /ai/chat ───────────────────────────────────────────────────────────────

def test_chat_unknown_handler(client: TestClient) -> None:
    response = client.post("/ai/chat", json={"handler": "unknown", "message": "hi"})
    assert response.status_code == 400
    assert "Unknown handler" in response.json()["detail"]


def test_chat_jussispace_returns_reply(make_app: Callable[..., FastAPI]) -> None:
    client = _with_agent(make_app(), FakeAgent("Löysin 3 asuntoa sinulle."))
    response = client.post("/ai/chat", json={"handler": "jussispace", "message": "Haluan kolmion saunan kera."})
    assert response.status_code == 200
    assert response.json()["reply"] == "Löysin 3 asuntoa sinulle."


def test_chat_passes_language_and_history(make_app: Callable[..., FastAPI]) -> None:
    agent = FakeAgent("Here are results.")
    client = _with_agent(make_app(), agent)
    history = [{"role": "user", "content": "Hi"}, {"role": "assistant", "content": "Hello!"}]
    response = client.post(
        "/ai/chat",
        json={"handler": "jussispace", "message": "Show flats", "language": "en", "history": history},
    )
    assert response.status_code == 200
    message, language, turns = agent.calls[0]
    assert (message, language) == ("Show flats", "en")
    assert [(t.role, t.content) for t in turns] == [("user", "Hi"), ("assistant", "Hello!")]


def test_chat_agent_not_configured_returns_503(client: TestClient) -> None:
    """The real agent with no Gemini credentials answers 503, not a crash."""
    response = client.post("/ai/chat", json={"handler": "jussispace", "message": "test"})
    assert response.status_code == 503


def test_chat_agent_unexpected_error_returns_502(make_app: Callable[..., FastAPI]) -> None:
    client = _with_agent(make_app(), FakeAgent(error=Exception("model blew up")))
    response = client.post("/ai/chat", json={"handler": "jussispace", "message": "test"})
    assert response.status_code == 502
    assert response.json()["detail"].startswith("Agent error:")
