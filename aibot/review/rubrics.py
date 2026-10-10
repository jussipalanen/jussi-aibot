"""
Review rubrics from `config/rubrics/*.yaml` and the generic review flow.
"""
import re
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from aibot.configfile import load_yaml_dir
from aibot.llm import LLMProvider, Message, ProviderError
from aibot.review import cv_fi
from aibot.review.extract import FILE_HEADER
from aibot.review.languages import detect_language

DOCUMENT_PLACEHOLDER = "{document_text}"
MAX_SUGGESTIONS = 10
MAX_SECURITY_ISSUES = 10
VERDICTS = ("ready", "needs_work", "not_ready")
SEVERITIES = ("low", "medium", "high", "critical")
RISKS = ("none", *SEVERITIES)
_LINE_PREFIX = re.compile(r"^ *\d+ \| ?", re.MULTILINE)


def number_lines(code: str) -> str:
    """Prefix each line with its number, e.g. ` 7 | return x`, so reviews can point to lines.

    Numbering restarts after each `==> name <==` file header.
    """
    lines = code.split("\n")
    width = len(str(len(lines)))
    numbered = []
    number = 0
    for line in lines:
        if FILE_HEADER.match(line):
            numbered.append(line)
            number = 0
        else:
            number += 1
            numbered.append(f"{number:>{width}} | {line}")
    return "\n".join(numbered)


class Rubric(BaseModel):
    """What to review, how to rate it and in which language to answer."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(pattern=r"^[a-z0-9][a-z0-9_-]{0,63}$")
    name: str
    description: str = ""
    language: str
    labels: list[str] = Field(min_length=6, max_length=6)
    prompt: str
    max_chars: int = Field(6000, ge=0)
    # "code": source files are accepted, formatting is kept and lines are numbered.
    input: Literal["document", "code"] = "document"
    heuristics: Literal["cv_fi"] | None = None

    @field_validator("prompt")
    @classmethod
    def _has_placeholder(cls, value: str) -> str:
        if DOCUMENT_PLACEHOLDER not in value:
            raise ValueError(f"prompt must contain {DOCUMENT_PLACEHOLDER}")
        return value

    def build_prompt(self, document_text: str) -> str:
        """Insert the (possibly truncated) document text into the prompt."""
        text = document_text[:self.max_chars] if self.max_chars else document_text
        if self.input == "code":
            text = number_lines(text)
        return self.prompt.replace(DOCUMENT_PLACEHOLDER, text)


def load_rubrics(directory: Path) -> dict[str, Rubric]:
    """Parse and validate every rubric file in a directory."""
    rubrics: dict[str, Rubric] = {}
    for path, data in load_yaml_dir(directory):
        try:
            rubric = Rubric.model_validate(data)
        except ValidationError as exc:
            raise ValueError(f"Invalid rubric config {path.name}:\n{exc}") from exc
        if rubric.id in rubrics:
            raise ValueError(f"Duplicate rubric id '{rubric.id}'.")
        rubrics[rubric.id] = rubric
    return rubrics


def _string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def code_languages(document: str) -> list[str]:
    """Languages in a code document: one per `==> name <==` file, or the pasted code as a whole."""
    parts = FILE_HEADER.split(document)
    # split() gives [text before the first header, name, code, name, code, ...]
    sections = [(None, document)] if len(parts) == 1 else list(zip(parts[1::2], parts[2::2]))
    languages: list[str] = []
    for filename, code in sections:
        language = detect_language(code, filename)
        if language and language not in languages:
            languages.append(language)
    return languages


def _snippet(value: object) -> str:
    """Code from a suggestion, without the line numbers the model may have copied."""
    return _LINE_PREFIX.sub("", str(value or "")).strip("\n")


def _line(value: object) -> int | None:
    try:
        line = int(value) if value is not None else None
    except (TypeError, ValueError):
        return None
    return line if line and line > 0 else None


def _security(value: object) -> dict:
    """The security risk and the vulnerabilities found, most severe first.

    The overall risk is never lower than the most severe issue, whatever the model says.
    """
    data = value if isinstance(value, dict) else {}
    issues = []
    for item in data.get("issues") if isinstance(data.get("issues"), list) else []:
        if not isinstance(item, dict):
            continue
        title = str(item.get("title") or "").strip()
        severity = str(item.get("severity") or "").strip().lower()
        if not title or severity not in SEVERITIES:
            continue
        cwe = str(item.get("cwe") or "").strip().upper()
        issues.append({
            "severity": severity,
            "title": title,
            "detail": str(item.get("detail") or "").strip(),
            "file": str(item.get("file") or "").strip() or None,
            "line": _line(item.get("line")),
            "cwe": cwe if re.fullmatch(r"CWE-\d{1,5}", cwe) else None,
        })
    issues.sort(key=lambda issue: SEVERITIES.index(issue["severity"]), reverse=True)
    issues = issues[:MAX_SECURITY_ISSUES]

    risk = str(data.get("risk") or "").strip().lower()
    risk = risk if risk in RISKS else "none"
    worst = issues[0]["severity"] if issues else "none"
    if RISKS.index(worst) > RISKS.index(risk):
        risk = worst
    return {"risk": risk, "issues": issues}


def _production(value: object, security: dict) -> dict | None:
    """Whether the code can go to production. High or critical security risk always means not ready."""
    data = value if isinstance(value, dict) else {}
    verdict = str(data.get("verdict") or "").strip().lower()
    if verdict not in VERDICTS:
        return None
    reason = str(data.get("reason") or "").strip()
    if security["risk"] in ("high", "critical") and verdict != "not_ready":
        verdict = "not_ready"
    return {"verdict": verdict, "reason": reason}


def _suggestions(value: object) -> list[dict]:
    """Code changes the model proposes: what is wrong, the current code and its replacement."""
    if not isinstance(value, list):
        return []
    result = []
    for item in value:
        if not isinstance(item, dict):
            continue
        replacement = _snippet(item.get("replacement"))
        issue = str(item.get("issue") or "").strip()
        if not replacement or not issue:
            continue
        result.append({
            "file": str(item.get("file") or "").strip() or None,
            "line": _line(item.get("line")),
            "issue": issue,
            "original": _snippet(item.get("original")),
            "replacement": replacement,
        })
    return result[:MAX_SUGGESTIONS]


async def review_document(
    rubric: Rubric,
    document_text: str,
    provider: LLMProvider,
    model: str | None = None,
) -> dict:
    """Review a document against a rubric and return a normalized result."""
    response = await provider.generate(
        [Message(role="user", content=rubric.build_prompt(document_text))],
        model=model,
        json_output=True,
    )
    parsed = cv_fi.extract_json_from_text(response.text) or {}

    if parsed.get("stars") is not None:
        try:
            stars = int(float(parsed["stars"]))
        except (TypeError, ValueError):
            stars = 0
        stars = max(0, min(5, stars))
        summary = str(parsed.get("summary") or "").strip()
        strengths = _string_list(parsed.get("strengths"))
        weaknesses = _string_list(parsed.get("weaknesses"))
    elif rubric.heuristics == "cv_fi":
        heuristic = cv_fi.analyze_resume_heuristics(document_text)
        stars = heuristic["stars"]
        summary = response.text.strip()[:500]
        strengths = heuristic["strengths"]
        weaknesses = heuristic["weaknesses"]
    else:
        raise ProviderError("The model did not return a valid review.")

    code = rubric.input == "code"
    security = _security(parsed.get("security")) if code else None
    return {
        "rubric": rubric.id,
        "language": rubric.language,
        "provider": provider.name,
        "stars": stars,
        "rating_text": rubric.labels[stars],
        "summary": summary,
        "strengths": strengths,
        "weaknesses": weaknesses,
        "languages": code_languages(document_text) if code else [],
        "production": _production(parsed.get("production"), security) if code else None,
        "security": security,
        "suggestions": _suggestions(parsed.get("suggestions")),
    }
