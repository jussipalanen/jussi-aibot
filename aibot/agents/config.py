"""
Schema for agent definitions in `config/agents/*.yaml`.
"""
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

_ID_PATTERN = r"^[a-z0-9][a-z0-9_-]{0,63}$"
_TOOL_NAME_PATTERN = r"^[A-Za-z_][A-Za-z0-9_]{0,63}$"

DEFAULT_LANGUAGE_INSTRUCTION = "Always respond in the same language the user writes in."


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class AuthConfig(_Strict):
    """How a tool authenticates against its backend.

    - `none`: no authentication
    - `bearer`: static token sent as `Authorization: Bearer <token>`
    - `header`: static header, e.g. `X-API-Key: <value>`
    - `login`: POST `body` to `login_url`, read the token from `token_field`,
      send it as a bearer token, and log in again after a 401
    """

    type: Literal["none", "bearer", "header", "login"] = "none"
    token: str = ""
    header: str = "Authorization"
    value: str = ""
    login_url: str = ""
    body: dict[str, Any] = Field(default_factory=dict)
    token_field: str = "token"


class PaginateConfig(_Strict):
    """Fetch every page of a paginated list endpoint and merge the results."""

    page_param: str = "page"
    limit_param: str = "limit"
    page_size: int = Field(50, ge=1, le=1000)
    data_field: str = "data"
    total_pages_field: str = "totalPages"
    max_pages: int = Field(20, ge=1, le=200)


class HttpConfig(_Strict):
    """The HTTP request a tool makes. `{name}` in the URL is filled from the tool arguments."""

    method: Literal["GET", "POST", "PUT", "PATCH", "DELETE"] = "GET"
    url: str
    auth: str | None = None
    headers: dict[str, str] = Field(default_factory=dict)
    paginate: PaginateConfig | None = None
    timeout: float = Field(10.0, gt=0, le=120)


class RagConfig(_Strict):
    """Rank a list result by similarity to the user's message and keep the best matches."""

    data_field: str = "data"
    top_k: int = Field(3, ge=1, le=50)
    fields: list[str] | None = None
    max_text_length: int = Field(1000, ge=0)


class ToolConfig(_Strict):
    """A tool the model can call."""

    name: str = Field(pattern=_TOOL_NAME_PATTERN)
    description: str
    parameters: dict[str, Any] = Field(default_factory=lambda: {"type": "object", "properties": {}})
    http: HttpConfig
    rag: RagConfig | None = None
    max_result_chars: int = Field(50000, ge=1000)

    @field_validator("parameters")
    @classmethod
    def _object_schema(cls, value: dict[str, Any]) -> dict[str, Any]:
        if value.get("type") != "object":
            raise ValueError("parameters must be a JSON Schema with type: object")
        value.setdefault("properties", {})
        return value


class ContextConfig(_Strict):
    """Data fetched from a URL and added to the system prompt (e.g. a CV or an FAQ)."""

    name: str = Field(pattern=_ID_PATTERN)
    title: str
    url: str
    headers: dict[str, str] = Field(default_factory=dict)
    ttl: int = Field(300, ge=0)
    fields: list[str] | None = None
    exclude: list[str] = Field(default_factory=list)
    max_text_length: int = Field(0, ge=0)
    asset_base_url: str = ""
    asset_fields: list[str] = Field(default_factory=list)


class EmbeddingConfig(_Strict):
    """Provider and model used for RAG embeddings."""

    provider: str = ""
    model: str = ""


class AgentConfig(_Strict):
    """A complete agent definition."""

    id: str = Field(pattern=_ID_PATTERN)
    name: str
    description: str = ""
    provider: str = "gemini"
    model: str = ""
    temperature: float | None = Field(None, ge=0, le=2)
    system_prompt: str
    language_instructions: dict[str, str] = Field(default_factory=dict)
    auth: dict[str, AuthConfig] = Field(default_factory=dict)
    tools: list[ToolConfig] = Field(default_factory=list)
    context: list[ContextConfig] = Field(default_factory=list)
    embedding: EmbeddingConfig = Field(default_factory=EmbeddingConfig)
    max_steps: int = Field(6, ge=1, le=20)
    history_limit: int = Field(10, ge=0, le=100)

    @model_validator(mode="after")
    def _check_references(self) -> "AgentConfig":
        names = [tool.name for tool in self.tools]
        duplicates = {name for name in names if names.count(name) > 1}
        if duplicates:
            raise ValueError(f"duplicate tool names: {', '.join(sorted(duplicates))}")
        for tool in self.tools:
            if tool.http.auth and tool.http.auth not in self.auth:
                raise ValueError(f"tool '{tool.name}' uses unknown auth profile '{tool.http.auth}'")
        return self

    def language_instruction(self, language: str | None) -> str:
        """Instruction for the requested language, or 'mirror the user' by default."""
        if language and language in self.language_instructions:
            return self.language_instructions[language]
        return DEFAULT_LANGUAGE_INSTRUCTION
