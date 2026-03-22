"""
Unit tests for pure service functions (no external I/O required).
"""
import pytest
from services import (
    normalize_whitespace,
    extract_json_from_text,
    map_rating_text,
    analyze_resume_heuristics,
    build_review_response,
    beautify_provider_output,
    format_summary_by_rating,
    _extract_puter_text,
)
from fastapi import HTTPException


# ── normalize_whitespace ───────────────────────────────────────────────────

def test_normalize_whitespace_collapses_spaces() -> None:
    assert normalize_whitespace("hello   world") == "hello world"

def test_normalize_whitespace_collapses_newlines() -> None:
    assert normalize_whitespace("hello\n\nworld") == "hello world"

def test_normalize_whitespace_strips_edges() -> None:
    assert normalize_whitespace("  hi  ") == "hi"

def test_normalize_whitespace_empty() -> None:
    assert normalize_whitespace("") == ""


# ── extract_json_from_text ─────────────────────────────────────────────────

def test_extract_json_valid() -> None:
    result = extract_json_from_text('Some text {"stars": 4, "summary": "ok"} trailing')
    assert result == {"stars": 4, "summary": "ok"}

def test_extract_json_no_json() -> None:
    assert extract_json_from_text("no json here") is None

def test_extract_json_invalid_json() -> None:
    assert extract_json_from_text("{broken json}") is None

def test_extract_json_nested() -> None:
    result = extract_json_from_text('{"stars": 3, "strengths": ["a", "b"]}')
    assert result["strengths"] == ["a", "b"]


# ── map_rating_text ────────────────────────────────────────────────────────

@pytest.mark.parametrize("stars,expected", [
    (5, "Erinomainen"),
    (4, "Erittäin hyvä"),
    (3, "Hyvä"),
    (2, "Tyydyttävä"),
    (1, "Heikko"),
    (0, "Huono"),
])
def test_map_rating_text(stars: int, expected: str) -> None:
    assert map_rating_text(stars) == expected


# ── analyze_resume_heuristics ──────────────────────────────────────────────

def test_heuristics_very_short_text() -> None:
    result = analyze_resume_heuristics("Nimi Testi")
    assert result["stars"] == 1
    assert isinstance(result["weaknesses"], list)

def test_heuristics_rich_text() -> None:
    text = (
        "Nimi: Matti Meikäläinen\n"
        "Kokemus: 5 vuotta ohjelmistokehityksessä, projekti vastuualue johtaminen\n"
        "Koulutus: Tietojenkäsittelytieteen maisteri, yliopisto\n"
        "Osaaminen: Python, Java, taidot kielet\n"
        "Yhteystiedot: matti@example.com puhelin 040-1234567\n"
        "Saavutukset: parannus 30% kasvu tulos " + "teksti " * 100
    )
    result = analyze_resume_heuristics(text)
    assert result["stars"] >= 3
    assert len(result["strengths"]) > 0

def test_heuristics_returns_required_keys() -> None:
    result = analyze_resume_heuristics("teksti")
    assert {"stars", "rating_text", "summary", "strengths", "weaknesses"} <= result.keys()

def test_heuristics_stars_clamped() -> None:
    result = analyze_resume_heuristics("x" * 5000)
    assert 0 <= result["stars"] <= 5


# ── build_review_response ──────────────────────────────────────────────────

def test_build_review_response_with_valid_json() -> None:
    output = '{"stars": 4, "rating_text": "Erittäin hyvä", "summary": "Hyvä CV", "strengths": ["Kokemus"], "weaknesses": ["Lyhyt"]}'
    result = build_review_response("parsed text", output, provider="puter_ai")
    assert result["stars"] == 4
    assert result["provider"] == "puter_ai"
    assert isinstance(result["strengths"], list)

def test_build_review_response_falls_back_to_heuristics() -> None:
    result = build_review_response("Nimi Testi kokemus koulutus", "no json here", provider="puter_ai")
    assert 0 <= result["stars"] <= 5
    assert "rating_text" in result

def test_build_review_response_clamps_stars() -> None:
    output = '{"stars": 99, "rating_text": "Erinomainen", "summary": "x", "strengths": [], "weaknesses": []}'
    result = build_review_response("text", output, provider="vertex_ai")
    assert result["stars"] <= 5

def test_build_review_response_default_provider_formats_output() -> None:
    result = build_review_response("some resume text", "no json", provider="default")
    assert isinstance(result["provider_raw_output"], str)


# ── beautify_provider_output ───────────────────────────────────────────────

def test_beautify_removes_markdown_bold() -> None:
    assert "**" not in beautify_provider_output("**bold text** here")

def test_beautify_removes_markdown_italic() -> None:
    assert "*" not in beautify_provider_output("*italic*")

def test_beautify_capitalizes_first_letter() -> None:
    result = beautify_provider_output("lowercase start")
    assert result[0].isupper()

def test_beautify_empty_string() -> None:
    assert beautify_provider_output("") == ""


# ── format_summary_by_rating ───────────────────────────────────────────────

@pytest.mark.parametrize("rating", ["Erinomainen", "Erittäin hyvä", "Hyvä", "Tyydyttävä", "Heikko", "Huono"])
def test_format_summary_contains_rating(rating: str) -> None:
    result = format_summary_by_rating(rating, "base summary")
    assert rating in result

def test_format_summary_unknown_rating() -> None:
    result = format_summary_by_rating("Unknown", "base")
    assert "base" in result


# ── _extract_puter_text ────────────────────────────────────────────────────

def test_extract_puter_text_string() -> None:
    assert _extract_puter_text("  hello  ") == "hello"

def test_extract_puter_text_nested_dict() -> None:
    response = {"result": {"message": {"content": "review text"}}}
    assert _extract_puter_text(response) == "review text"

def test_extract_puter_text_choices_format() -> None:
    response = {"choices": [{"message": {"content": "choice text"}}]}
    assert _extract_puter_text(response) == "choice text"

def test_extract_puter_text_error_payload_raises() -> None:
    response = {"success": False, "error": "rate limited"}
    with pytest.raises(HTTPException) as exc_info:
        _extract_puter_text(response)
    assert exc_info.value.status_code == 502

def test_extract_puter_text_unreadable_raises() -> None:
    with pytest.raises(HTTPException) as exc_info:
        _extract_puter_text({"unknown": "shape"})
    assert exc_info.value.status_code == 502
