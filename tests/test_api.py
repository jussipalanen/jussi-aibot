"""
API endpoint tests using FastAPI's TestClient.
External AI providers are mocked so no real credentials are needed.
"""
import io
from unittest.mock import patch, MagicMock

import pytest
from fastapi.testclient import TestClient


# ── Basic endpoints ────────────────────────────────────────────────────────

def test_root(client: TestClient) -> None:
    response = client.get("/")
    assert response.status_code == 200
    assert "message" in response.json()


def test_health(client: TestClient) -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_version(client: TestClient) -> None:
    response = client.get("/version")
    assert response.status_code == 200
    data = response.json()
    assert "python_version" in data
    assert "fastapi_version" in data


def test_robots_txt(client: TestClient) -> None:
    response = client.get("/robots.txt")
    assert response.status_code == 200
    assert "Disallow" in response.text


def test_robots_header_present(client: TestClient) -> None:
    response = client.get("/health")
    assert "noindex" in response.headers.get("x-robots-tag", "")


# ── /ai/review — input validation ─────────────────────────────────────────

def test_review_missing_file(client: TestClient) -> None:
    response = client.post("/ai/review")
    assert response.status_code == 422


def test_review_unsupported_extension(client: TestClient) -> None:
    response = client.post(
        "/ai/review",
        files={"file": ("resume.txt", b"some content", "text/plain")},
    )
    assert response.status_code == 400
    assert "Unsupported file type" in response.json()["detail"]


def test_review_empty_filename(client: TestClient) -> None:
    response = client.post(
        "/ai/review",
        files={"file": ("", b"content", "application/octet-stream")},
    )
    assert response.status_code in (400, 422)


def test_review_invalid_provider(client: TestClient) -> None:
    response = client.post(
        "/ai/review",
        data={"provider": "nonexistent_provider"},
        files={"file": ("resume.pdf", b"%PDF fake", "application/pdf")},
    )
    assert response.status_code == 400
    assert "provider" in response.json()["detail"].lower()


# ── /ai/review — provider flows (mocked) ──────────────────────────────────

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


def test_review_puter_ai_success(client: TestClient) -> None:
    with (
        patch("routes.extract_resume_text", return_value="Nimi Matti Meikäläinen kokemus koulutus osaaminen"),
        patch("routes.generate_review_puter_ai", return_value=_MOCK_REVIEW_JSON),
    ):
        response = client.post(
            "/ai/review",
            data={"provider": "puter_ai"},
            files={"file": ("resume.pdf", _MINIMAL_PDF, "application/pdf")},
        )
    assert response.status_code == 200
    data = response.json()
    assert data["stars"] == 4
    assert isinstance(data["strengths"], list)


def test_review_vertex_ai_success(client: TestClient) -> None:
    with (
        patch("routes.extract_resume_text", return_value="Nimi Matti kokemus koulutus osaaminen"),
        patch("routes.generate_review_vertex_ai", return_value=_MOCK_REVIEW_JSON),
    ):
        response = client.post(
            "/ai/review",
            data={"provider": "vertex_ai"},
            files={"file": ("resume.docx", b"fake docx", "application/vnd.openxmlformats-officedocument.wordprocessingml.document")},
        )
    assert response.status_code == 200
    assert response.status_code == 200


def test_review_puter_ai_missing_key(client: TestClient) -> None:
    """Without PUTER_API_KEY the service should return 503."""
    with patch("routes.extract_resume_text", return_value="some text"):
        response = client.post(
            "/ai/review",
            data={"provider": "puter_ai"},
            files={"file": ("resume.pdf", _MINIMAL_PDF, "application/pdf")},
        )
    assert response.status_code == 503


def test_review_response_shape(client: TestClient) -> None:
    with (
        patch("routes.extract_resume_text", return_value="Nimi kokemus koulutus osaaminen"),
        patch("routes.generate_review_puter_ai", return_value=_MOCK_REVIEW_JSON),
    ):
        response = client.post(
            "/ai/review",
            data={"provider": "puter_ai"},
            files={"file": ("resume.pdf", _MINIMAL_PDF, "application/pdf")},
        )
    assert response.status_code == 200
    data = response.json()
    for key in ("stars", "rating_text", "summary", "strengths", "weaknesses", "provider_raw_output"):
        assert key in data, f"Missing key: {key}"


# ── /ai/chat ───────────────────────────────────────────────────────────────

def test_chat_unknown_handler(client: TestClient) -> None:
    response = client.post("/ai/chat", json={"handler": "unknown", "message": "hi"})
    assert response.status_code == 400
    assert "Unknown handler" in response.json()["detail"]


def test_chat_jussispace_returns_reply(client: TestClient) -> None:
    with patch("agent.agent.ask", return_value="Löysin 3 asuntoa sinulle."):
        response = client.post(
            "/ai/chat",
            json={"handler": "jussispace", "message": "Haluan kolmen kimppaa saunan kera."},
        )
    assert response.status_code == 200
    assert response.json()["reply"] == "Löysin 3 asuntoa sinulle."


def test_chat_jussispace_with_language(client: TestClient) -> None:
    with patch("agent.agent.ask", return_value="Here are some properties.") as mock_ask:
        response = client.post(
            "/ai/chat",
            json={"handler": "jussispace", "message": "Find me a flat", "language": "en"},
        )
    assert response.status_code == 200
    mock_ask.assert_called_once_with("Find me a flat", language="en", history=[])


def test_chat_jussispace_with_history(client: TestClient) -> None:
    history = [{"role": "user", "content": "Hi"}, {"role": "assistant", "content": "Hello!"}]
    with patch("agent.agent.ask", return_value="Here are results.") as mock_ask:
        response = client.post(
            "/ai/chat",
            json={"handler": "jussispace", "message": "Show flats", "history": history},
        )
    assert response.status_code == 200
    mock_ask.assert_called_once_with("Show flats", language=None, history=history)


def test_chat_agent_runtime_error_returns_503(client: TestClient) -> None:
    with patch("agent.agent.ask", side_effect=RuntimeError("GCP_PROJECT not set")):
        response = client.post(
            "/ai/chat",
            json={"handler": "jussispace", "message": "test"},
        )
    assert response.status_code == 503


def test_chat_agent_unexpected_error_returns_502(client: TestClient) -> None:
    with patch("agent.agent.ask", side_effect=Exception("Vertex AI blew up")):
        response = client.post(
            "/ai/chat",
            json={"handler": "jussispace", "message": "test"},
        )
    assert response.status_code == 502


