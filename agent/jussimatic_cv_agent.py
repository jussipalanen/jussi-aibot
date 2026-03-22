"""
Jussimatic AI CV Chat agent.
Fetches Jussi Alanen's CV from the API and answers questions about it.
"""
import os
import time
from urllib.parse import urlparse

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


def _resolve_image_url(path: str) -> str:
    """Resolve a relative image path to an absolute URL using the storage base URL."""
    if not path:
        return ""
    if path.startswith("http://") or path.startswith("https://"):
        return path
    base = os.getenv("JUSSILOG_STORAGE_BASE_URL", "").strip().rstrip("/")
    if base:
        return f"{base}/{path.lstrip('/')}"
    return path


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
    if cv.get("photo"):
        lines.append(f"Profile image: {_resolve_image_url(cv['photo'])}")
    if cv.get("photo_sizes"):
        sizes = cv["photo_sizes"]
        if sizes.get("medium"):
            lines.append(f"Profile image (medium): {_resolve_image_url(sizes['medium'])}")

    # Summary
    if cv.get("summary"):
        lines.append(f"\nSummary:\n{cv['summary']}")

    # Work experience
    if cv.get("work_experiences"):
        lines.append("\nWork Experience:")
        for exp in cv.get("work_experiences", []):
            start = (exp.get("start_date") or "")[:7]
            end = "Present" if exp.get("is_current") else (exp.get("end_date") or "")[:7]
            lines.append(f"\n  Company:  {exp.get('company_name', '')}")
            lines.append(f"  Role:     {exp.get('job_title', '')}")
            lines.append(f"  Period:   {start} – {end}")
            if exp.get("location"):
                lines.append(f"  Location: {exp['location']}")
            if exp.get("description"):
                lines.append(f"  About:    {exp['description'][:400]}")

    # Education
    if cv.get("educations"):
        lines.append("\nEducation:")
        for edu in cv.get("educations", []):
            lines.append(f"\n  School:   {edu.get('institution_name', '')}")
            lines.append(f"  Degree:   {edu.get('degree', '')} – {edu.get('field_of_study', '')}")
            if edu.get("graduation_year"):
                lines.append(f"  Graduated: {edu['graduation_year']}")
            if edu.get("location"):
                lines.append(f"  Location: {edu['location']}")

    # Skills grouped by category
    _CATEGORY_LABELS: dict[str, str] = {
        "fi": {
            "programming_languages": "Ohjelmointikielet",
            "frameworks": "Sovelluskehykset",
            "libraries": "Kirjastot",
            "databases": "Tietokannat",
            "cloud_platforms": "Pilvipalvelut",
            "serverless": "Serverless",
            "ci_cd": "CI/CD",
            "configuration_management": "Konfiguraationhallinta",
            "version_control": "Versionhallinta",
            "testing_qa": "Testaus & laadunvarmistus",
            "machine_learning_ai": "Tekoäly & koneoppiminen",
            "operating_systems": "Käyttöjärjestelmät",
            "project_management": "Projektinhallinta",
            "ui_ux_design": "UI/UX-suunnittelu",
            "other": "Muut",
        },
        "en": {
            "programming_languages": "Programming Languages",
            "frameworks": "Frameworks",
            "libraries": "Libraries",
            "databases": "Databases",
            "cloud_platforms": "Cloud Platforms",
            "serverless": "Serverless",
            "ci_cd": "CI/CD",
            "configuration_management": "Configuration Management",
            "version_control": "Version Control",
            "testing_qa": "Testing & QA",
            "machine_learning_ai": "Machine Learning & AI",
            "operating_systems": "Operating Systems",
            "project_management": "Project Management",
            "ui_ux_design": "UI/UX Design",
            "other": "Other",
        },
    }
    cv_lang = cv.get("language", "en")
    labels = _CATEGORY_LABELS.get(cv_lang, _CATEGORY_LABELS["en"])
    show_skill_levels = cv.get("show_skill_levels", True)
    if cv.get("skills"):
        lines.append("\nSkills:")
        skills_by_cat: dict[str, list[str]] = {}
        for skill in cv.get("skills", []):
            cat = skill.get("category", "other")
            entry = skill["name"] if not show_skill_levels else f"{skill['name']} ({skill.get('proficiency', '')})"
            skills_by_cat.setdefault(cat, []).append(entry)
        for cat, cat_skills in skills_by_cat.items():
            label = labels.get(cat, cat.replace("_", " ").title())
            lines.append(f"  {label}: {', '.join(cat_skills)}")

    # Languages
    show_language_levels = cv.get("show_language_levels", True)
    if cv.get("languages"):
        lines.append("\nLanguages:")
        for lang in cv.get("languages", []):
            entry = lang.get("language", "") if not show_language_levels else f"{lang.get('language', '')} ({lang.get('proficiency', '')})"
            lines.append(f"  - {entry}")

    # Awards
    if cv.get("awards"):
        lines.append("\nAwards:")
        for award in cv.get("awards", []):
            lines.append(f"\n  Title: {award.get('title', '')}")
            if award.get("issuer"):
                lines.append(f"  Issuer: {award['issuer']}")
            if award.get("date"):
                lines.append(f"  Date: {award['date'][:10]}")
            if award.get("description"):
                lines.append(f"  Description: {award['description']}")

    # Projects
    if cv.get("projects"):
        lines.append("\nProjects:")
        for project in cv.get("projects", []):
            lines.append(f"\n  Name: {project.get('name', '')}")
            if project.get("description"):
                lines.append(f"  Description: {project['description']}")
            if project.get("url"):
                lines.append(f"  URL: {project['url']}")

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

    photo_url = _resolve_image_url(cv_data.get("photo", ""))
    photo_instruction = (
        f"When introducing Jussi, follow this exact structure:\n"
        f"1. Write exactly ONE short sentence introducing his name and title.\n"
        f"2. On the next line, output ONLY this tag: [photo]{photo_url}[/photo]\n"
        f"3. Then continue with the rest of the introduction and details.\n"
        f"Do NOT write more than one sentence before the [photo] tag.\n"
        if photo_url else ""
    )

    system_prompt = (
        "You are a helpful AI assistant representing Jussi Alanen's CV and professional background.\n"
        "Answer questions about Jussi's skills, work experience, education, awards, and contact details.\n"
        "Be friendly, professional and concise. Base your answers only on the CV data provided.\n"
        "If asked about something not in the CV, say you don't have that information.\n"
        f"{photo_instruction}"
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
