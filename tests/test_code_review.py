"""
Code reviews: source file uploads, several files at once, kept formatting and suggested changes.
"""
import json
from collections.abc import Callable

from fastapi import FastAPI
from fastapi.testclient import TestClient

from aibot.review.extract import is_code_file, normalize_code
from aibot.review.rubrics import _suggestions, number_lines
from tests.conftest import FakeProvider

PY_CODE = "def total(items):\n    result = 0\n    for item in items:\n        result += item\n    return result\n"
JS_CODE = "export function greet(name) {\n  return 'Hello ' + name;\n}\n"
REVIEW = {
    "stars": 3,
    "summary": "Python code that sums a list.",
    "strengths": ["Short"],
    "weaknesses": ["app.py line 2: reimplements sum()"],
    "suggestions": [{
        "file": "app.py",
        "line": 2,
        "issue": "Use the built-in sum().",
        "original": "2 |     result = 0\n3 |     for item in items:\n4 |         result += item\n5 |     return result",
        "replacement": "    return sum(items)",
    }],
}


def _setup(make_app: Callable[..., FastAPI], review: dict | None = None) -> tuple[TestClient, FakeProvider]:
    gemini = FakeProvider(text=json.dumps(review or REVIEW))
    return TestClient(make_app(providers={"gemini": gemini}), raise_server_exceptions=False), gemini


def _prompt(gemini: FakeProvider) -> str:
    return gemini.calls[0]["messages"][0].content


# ── Helpers ────────────────────────────────────────────────────────────────

def test_normalize_code_keeps_indentation() -> None:
    assert normalize_code("\r\n\ndef f():\r\n    return 1   \r\n\n") == "def f():\n    return 1"


def test_number_lines_restarts_for_each_file() -> None:
    numbered = number_lines("==> a.py <==\nx = 1\ny = 2\n\n==> b.js <==\nlet z;")
    assert numbered.split("\n") == ["==> a.py <==", "1 | x = 1", "2 | y = 2", "3 | ", "==> b.js <==", "1 | let z;"]


def test_is_code_file() -> None:
    assert is_code_file("src/app.py") and is_code_file("Main.java") and is_code_file("Dockerfile")
    assert not is_code_file("cv.pdf") and not is_code_file("notes") and not is_code_file("image.png")


def test_suggestions_are_cleaned() -> None:
    result = _suggestions([
        REVIEW["suggestions"][0],
        {"issue": "No replacement"},
        {"replacement": "x = 1"},
        "not an object",
        {"issue": "Bad line", "line": "abc", "replacement": "y = 2"},
    ])
    assert len(result) == 2
    assert result[0]["original"].startswith("    result = 0\n    for item")  # line numbers removed
    assert result[0]["file"] == "app.py" and result[0]["line"] == 2
    assert result[1]["line"] is None and result[1]["file"] is None


# ── API ────────────────────────────────────────────────────────────────────

def test_code_rubrics_are_listed(client: TestClient) -> None:
    ids = {r["id"] for r in client.get("/v1/review/rubrics").json()}
    assert {"code-review-en", "code-review-fi"} <= ids


def test_review_pasted_code_keeps_formatting(make_app: Callable[..., FastAPI]) -> None:
    client, gemini = _setup(make_app)
    response = client.post("/v1/review", data={"rubric": "code-review-en", "text": PY_CODE})
    assert response.status_code == 200
    body = response.json()
    assert body["stars"] == 3
    assert body["suggestions"] == [{
        "file": "app.py",
        "line": 2,
        "issue": "Use the built-in sum().",
        "original": "    result = 0\n    for item in items:\n        result += item\n    return result",
        "replacement": "    return sum(items)",
    }]
    prompt = _prompt(gemini)
    assert "1 | def total(items):\n2 |     result = 0" in prompt


def test_review_several_code_files(make_app: Callable[..., FastAPI]) -> None:
    client, gemini = _setup(make_app)
    response = client.post(
        "/v1/review",
        data={"rubric": "code-review-fi"},
        files=[("file", ("app.py", PY_CODE.encode(), "text/x-python")),
               ("file", ("greet.js", JS_CODE.encode(), "text/javascript"))],
    )
    assert response.status_code == 200
    assert response.json()["language"] == "fi"
    prompt = _prompt(gemini)
    # Numbers are padded to the widest one across all files.
    assert "==> app.py <==\n 1 | def total(items):" in prompt
    assert "==> greet.js <==\n 1 | export function greet(name) {" in prompt


def test_code_rubric_rejects_documents(make_app: Callable[..., FastAPI]) -> None:
    client, _ = _setup(make_app)
    response = client.post("/v1/review", data={"rubric": "code-review-en"},
                           files={"file": ("cv.pdf", b"%PDF", "application/pdf")})
    assert response.status_code == 400
    assert "cv.pdf" in response.json()["detail"]


def test_code_rubric_rejects_binary_files(make_app: Callable[..., FastAPI]) -> None:
    client, _ = _setup(make_app)
    response = client.post("/v1/review", data={"rubric": "code-review-en"},
                           files={"file": ("app.py", b"\x00\x01binary", "text/x-python")})
    assert response.status_code == 400
    assert "not a text file" in response.json()["detail"]


def test_code_rubric_limits_file_count(make_app: Callable[..., FastAPI]) -> None:
    client, _ = _setup(make_app)
    files = [("file", (f"f{i}.py", b"x = 1", "text/x-python")) for i in range(21)]
    response = client.post("/v1/review", data={"rubric": "code-review-en"}, files=files)
    assert response.status_code == 400
    assert "at most 20" in response.json()["detail"]


def test_document_rubric_takes_one_file(make_app: Callable[..., FastAPI]) -> None:
    client, _ = _setup(make_app)
    files = [("file", ("a.pdf", b"%PDF", "application/pdf")), ("file", ("b.pdf", b"%PDF", "application/pdf"))]
    response = client.post("/v1/review", data={"rubric": "cv-en"}, files=files)
    assert response.status_code == 400
    assert "one file" in response.json()["detail"]


def test_document_rubric_rejects_code_files(make_app: Callable[..., FastAPI]) -> None:
    client, _ = _setup(make_app)
    response = client.post("/v1/review", data={"rubric": "cv-en"},
                           files={"file": ("app.py", PY_CODE.encode(), "text/x-python")})
    assert response.status_code == 400


def test_document_reviews_have_no_suggestions(make_app: Callable[..., FastAPI]) -> None:
    client, _ = _setup(make_app, {"stars": 4, "summary": "Good", "strengths": [], "weaknesses": []})
    text = "Jane Doe. Software developer with five years of experience in Python and cloud services."
    response = client.post("/v1/review", data={"rubric": "cv-en", "text": text})
    assert response.status_code == 200
    assert response.json()["suggestions"] == []


def test_demo_page_knows_code_rubrics(client: TestClient) -> None:
    page = client.get("/demo/review").text
    start = page.index('type="application/json">') + len('type="application/json">')
    config = json.loads(page[start:page.index("</script>", start)])
    inputs = {r["id"]: r["input"] for r in config["rubrics"]}
    assert inputs["code-review-en"] == "code" and inputs["cv-en"] == "document"
    assert ".py" in config["codeExtensions"] and config["maxCodeFiles"] == 20
    assert 'id="suggestion-list"' in page
