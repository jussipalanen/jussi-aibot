"""
Jussimatic AI CV Chat agent.
Fetches Jussi Alanen's CV from the API and answers questions about it.
"""
import os
import time

import requests
import vertexai
from vertexai.generative_models import GenerativeModel

_SUPPORTED_LANGUAGES = {"fi", "en"}
_LANGUAGE_INSTRUCTIONS = {
    "fi": "Vastaa aina suomeksi.",
    "en": "Always respond in English.",
}

# Simple in-memory cache — refreshes every 5 minutes
_cv_cache: dict = {"data": None, "fetched_at": 0.0}
_CV_CACHE_TTL = 300


def _fetch_cv() -> dict:
    now = time.time()
    if _cv_cache["data"] and now - _cv_cache["fetched_at"] < _CV_CACHE_TTL:
        return _cv_cache["data"]

    url = os.getenv("JUSSIMATIC_CV_API_URL", "").strip()
    if not url:
        raise RuntimeError("JUSSIMATIC_CV_API_URL is not set.")

    response = requests.get(url, timeout=10)
    response.raise_for_status()
    data = response.json()

    _cv_cache["data"] = data
    _cv_cache["fetched_at"] = now
    return data


def _format_cv(cv: dict) -> str:
    """Build a compact plain-text representation of the CV for the model context."""
    lines = []

    # Basic info
    lines.append(f"Name: {cv.get('full_name', '')}")
    lines.append(f"Title: {cv.get('title', '')}")
    lines.append(f"Email: {cv.get('email', '')}")
    lines.append(f"Phone: {cv.get('phone', '')}")
    lines.append(f"Location: {cv.get('location', '')}")
    if cv.get("linkedin_url"):
        lines.append(f"LinkedIn: {cv['linkedin_url']}")
    if cv.get("portfolio_url"):
        lines.append(f"Portfolio: {cv['portfolio_url']}")
    if cv.get("github_url"):
        lines.append(f"GitHub: {cv['github_url']}")

    # Summary
    if cv.get("summary"):
        lines.append(f"\nSummary:\n{cv['summary']}")

    # Work experience
    lines.append("\nWork Experience:")
    for exp in cv.get("work_experiences", []):
        start = (exp.get("start_date") or "")[:7]
        end = "present" if exp.get("is_current") else (exp.get("end_date") or "")[:7]
        lines.append(f"- {exp['job_title']} at {exp['company_name']} ({start} – {end}), {exp.get('location', '')}")
        if exp.get("description"):
            lines.append(f"  {exp['description'][:400]}")

    # Education
    lines.append("\nEducation:")
    for edu in cv.get("educations", []):
        lines.append(
            f"- {edu.get('degree', '')} ({edu.get('field_of_study', '')}) "
            f"at {edu.get('institution_name', '')}, graduated {edu.get('graduation_year', '')}"
        )

    # Skills grouped by category
    lines.append("\nSkills:")
    skills_by_cat: dict[str, list[str]] = {}
    for skill in cv.get("skills", []):
        cat = skill.get("category", "other")
        skills_by_cat.setdefault(cat, []).append(f"{skill['name']} ({skill.get('proficiency', '')})")
    for cat, skills in skills_by_cat.items():
        lines.append(f"  {cat}: {', '.join(skills)}")

    # Languages
    lines.append("\nLanguages:")
    for lang in cv.get("languages", []):
        lines.append(f"- {lang.get('language', '')} ({lang.get('proficiency', '')})")

    # Awards
    if cv.get("awards"):
        lines.append("\nAwards:")
        for award in cv.get("awards", []):
            lines.append(f"- {award['title']}: {award.get('description', '')}")

    return "\n".join(lines)


def _init_vertexai() -> None:
    project = os.getenv("GCP_PROJECT", "").strip()
    location = os.getenv("AGENT_GCP_LOCATION", "europe-north1").strip() or "europe-north1"
    if not project:
        raise RuntimeError("GCP_PROJECT environment variable is not set.")
    vertexai.init(project=project, location=location)


def ask(
    user_message: str,
    language: str | None = None,
    history: list[dict] | None = None,
) -> str:
    """
    Answer a question about Jussi Alanen's CV.

    Args:
        user_message: The user's question.
        language: Optional — 'fi' or 'en'. Mirrors user language when omitted.
        history: Optional previous messages for multi-turn chat.
    """
    _init_vertexai()

    cv_data = _fetch_cv()
    cv_text = _format_cv(cv_data)

    if language and language in _SUPPORTED_LANGUAGES:
        lang_instruction = _LANGUAGE_INSTRUCTIONS[language]
    else:
        lang_instruction = "Always respond in the same language the user writes in."

    system_prompt = (
        "You are a helpful AI assistant representing Jussi Alanen's CV and professional background.\n"
        "Answer questions about Jussi's skills, work experience, education, awards, and contact details.\n"
        "Be friendly, professional and concise. Base your answers only on the CV data provided.\n"
        "If asked about something not in the CV, say you don't have that information.\n"
        f"{lang_instruction}\n\n"
        f"CV DATA:\n{cv_text}"
    )

    model_name = os.getenv("JUSSIMATIC_CV_VERTEX_MODEL", os.getenv("AGENT_VERTEX_MODEL", "gemini-2.5-flash-lite")).strip() or "gemini-2.5-flash-lite"
    model = GenerativeModel(model_name, system_instruction=system_prompt)

    # Keep last 10 history messages to cap token usage
    messages = [
        {"role": m["role"], "content": m["content"]}
        for m in (history or [])[-10:]
    ]
    messages.append({"role": "user", "content": user_message})

    conversation = "\n\n".join(
        f"{'User' if m['role'] == 'user' else 'Assistant'}: {m['content']}"
        for m in messages
    )

    response = model.generate_content(conversation)
    return response.text.strip()
