"""
The review demo page, plain-text reviews and demo access rules.
"""
import json
import re
from collections.abc import Callable

from fastapi import FastAPI
from fastapi.testclient import TestClient

from tests.conftest import FakeProvider

REVIEW_JSON = '{"stars": 4, "summary": "Good", "strengths": ["Clear"], "weaknesses": ["Short"]}'
CV_TEXT = "Jane Doe. Software developer with five years of experience in Python and cloud services."
SAME_ORIGIN = {"Origin": "http://testserver"}


def _client(make_app: Callable[..., FastAPI], **env: str) -> TestClient:
    app = make_app(env=env, providers={"gemini": FakeProvider(text=REVIEW_JSON)})
    return TestClient(app, raise_server_exceptions=False)


# ── Pages ──────────────────────────────────────────────────────────────────

def test_home_links_to_demo(client: TestClient) -> None:
    page = client.get("/").text
    assert 'href="/demo/review"' in page
    assert 'href="/docs"' in page
    assert client.get("/", headers={"accept": "application/json"}).json()["demos"] == ["/demo/review"]


def _page_config(page: str) -> dict:
    return json.loads(re.search(r'id="review-config" type="application/json">(.*?)</script>', page).group(1))


def test_demo_page(client: TestClient) -> None:
    response = client.get("/demo/review")
    assert response.status_code == 200
    page = response.text
    assert 'id="review-form"' in page
    assert 'id="file-input"' in page and 'id="text-input"' in page
    assert 'data-lang="fi"' in page and 'data-lang="en"' in page
    assert "{{" not in page
    config = _page_config(page)
    assert config["maxUploadMb"] == 50
    assert config["appName"] == "Jussi AI Bot"


def test_demo_page_has_finnish_and_english_rubrics(client: TestClient) -> None:
    rubrics = {r["id"]: r["language"] for r in _page_config(client.get("/demo/review").text)["rubrics"]}
    assert rubrics["cv-fi"] == "fi" and rubrics["cv-en"] == "en"
    assert rubrics["cover-letter-fi"] == "fi" and rubrics["cover-letter-en"] == "en"


def test_demo_config_cannot_break_out_of_script(make_app: Callable[..., FastAPI]) -> None:
    page = _client(make_app, APP_NAME="</script><script>alert(1)</script>").get("/demo/review").text
    assert "</script><script>alert(1)" not in page


def test_static_assets(client: TestClient) -> None:
    assert client.get("/static/review.js").status_code == 200
    css = client.get("/static/app.css")
    assert css.status_code == 200
    assert "text/css" in css.headers["content-type"]


def test_demo_can_be_disabled(make_app: Callable[..., FastAPI]) -> None:
    client = _client(make_app, DEMO_ENABLED="false")
    assert client.get("/demo/review").status_code == 404
    assert 'href="/demo/review"' not in client.get("/").text


# ── Plain-text reviews ─────────────────────────────────────────────────────

def test_review_text(make_app: Callable[..., FastAPI]) -> None:
    gemini = FakeProvider(text=REVIEW_JSON)
    client = TestClient(make_app(providers={"gemini": gemini}))
    response = client.post("/v1/review", data={"rubric": "cv-en", "text": f"  {CV_TEXT}\n\n "})
    assert response.status_code == 200
    assert response.json()["stars"] == 4
    assert CV_TEXT in gemini.calls[0]["messages"][0].content


def test_review_needs_file_or_text(make_app: Callable[..., FastAPI]) -> None:
    client = _client(make_app)
    response = client.post("/v1/review", data={"rubric": "cv-en", "text": "   "})
    assert response.status_code == 400
    assert "file or text" in response.json()["detail"]


def test_review_rejects_file_and_text(make_app: Callable[..., FastAPI]) -> None:
    client = _client(make_app)
    response = client.post(
        "/v1/review",
        data={"rubric": "cv-en", "text": CV_TEXT},
        files={"file": ("cv.pdf", b"%PDF", "application/pdf")},
    )
    assert response.status_code == 400
    assert "not both" in response.json()["detail"]


def test_review_text_too_long(make_app: Callable[..., FastAPI]) -> None:
    client = _client(make_app)
    response = client.post("/v1/review", data={"rubric": "cv-en", "text": "x" * 100_001})
    assert response.status_code == 413


# ── Demo access ────────────────────────────────────────────────────────────

def test_demo_needs_key_when_not_public(make_app: Callable[..., FastAPI]) -> None:
    client = _client(make_app, AI_SECRET_KEY="s3cret")
    response = client.post("/v1/review", data={"text": CV_TEXT}, headers=SAME_ORIGIN)
    assert response.status_code == 401


def test_demo_with_key_from_own_origin(make_app: Callable[..., FastAPI]) -> None:
    """A key works on the demo page even when ALLOWED_ORIGINS lists only other sites."""
    client = _client(make_app, AI_SECRET_KEY="s3cret", ALLOWED_ORIGINS="https://frontend.test")
    headers = {**SAME_ORIGIN, "Authorization": "Bearer s3cret"}
    assert client.post("/v1/review", data={"text": CV_TEXT}, headers=headers).status_code == 200
    other = {"Origin": "https://evil.test", "Authorization": "Bearer s3cret"}
    assert client.post("/v1/review", data={"text": CV_TEXT}, headers=other).status_code == 403


def test_public_demo_allows_same_origin_reviews_only(make_app: Callable[..., FastAPI]) -> None:
    client = _client(make_app, AI_SECRET_KEY="s3cret", DEMO_PUBLIC="true", DEMO_RATE_LIMIT="2/day")

    assert client.post("/v1/review", data={"text": CV_TEXT}, headers=SAME_ORIGIN).status_code == 200
    # Other origins and missing origins still need a key.
    assert client.post("/v1/review", data={"text": CV_TEXT}, headers={"Origin": "https://evil.test"}).status_code == 403
    assert client.post("/v1/review", data={"text": CV_TEXT}).status_code == 401
    # The demo client cannot use agents.
    chat = client.post("/v1/agents/jussispace/chat", json={"message": "hi"}, headers=SAME_ORIGIN)
    assert chat.status_code == 404
    # The demo has its own limit.
    assert client.post("/v1/review", data={"text": CV_TEXT}, headers=SAME_ORIGIN).status_code == 200
    limited = client.post("/v1/review", data={"text": CV_TEXT}, headers=SAME_ORIGIN)
    assert limited.status_code == 429
    assert "retry-after" in limited.headers
