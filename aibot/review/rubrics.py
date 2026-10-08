"""
Review rubrics from `config/rubrics/*.yaml` and the generic review flow.
"""
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from aibot.configfile import load_yaml_dir
from aibot.llm import LLMProvider, Message, ProviderError
from aibot.review import cv_fi

DOCUMENT_PLACEHOLDER = "{document_text}"


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

    return {
        "rubric": rubric.id,
        "language": rubric.language,
        "provider": provider.name,
        "stars": stars,
        "rating_text": rubric.labels[stars],
        "summary": summary,
        "strengths": strengths,
        "weaknesses": weaknesses,
    }
