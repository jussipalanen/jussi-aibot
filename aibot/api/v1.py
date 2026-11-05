"""
Version 1 of the platform API.
"""
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, File, Form, HTTPException, Path, Request, UploadFile, status
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from aibot.agents.engine import ChatTurn
from aibot.api.deps import (
    MAX_MESSAGE_CHARS,
    UserToken,
    call_ai,
    read_code_files,
    read_document,
    read_text,
    require_client,
    services,
)
from aibot.grounded import Passage, answer_from_passages
from aibot.review.rubrics import review_document
from aibot.security import Client

router = APIRouter(prefix="/v1")


class AgentInfo(BaseModel):
    id: str
    name: str
    description: str
    languages: list[str]


class HistoryMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(max_length=MAX_MESSAGE_CHARS)


class ChatBody(BaseModel):
    message: str = Field(min_length=1, max_length=MAX_MESSAGE_CHARS, examples=["Näytä vapaat asunnot Helsingissä"])
    language: str | None = Field(None, description="Language code from the agent's list; mirrors the user when omitted", examples=["fi"])
    history: list[HistoryMessage] = Field(default_factory=list, max_length=100)


class ChatReply(BaseModel):
    agent: str
    reply: str


class RubricInfo(BaseModel):
    id: str
    name: str
    description: str
    language: str
    labels: list[str]


class CodeSuggestion(BaseModel):
    file: str | None = Field(None, description="File name, when several files were reviewed")
    line: int | None = Field(None, description="First line of `original` in the reviewed code")
    issue: str = Field(description="What is wrong and why")
    original: str = Field(description="The current code; empty when code is added")
    replacement: str = Field(description="The code to use instead")


class ProductionVerdict(BaseModel):
    verdict: Literal["ready", "needs_work", "not_ready"] = Field(
        description="`not_ready` whenever the security risk is high or critical")
    reason: str


class SecurityIssue(BaseModel):
    severity: Literal["low", "medium", "high", "critical"]
    title: str
    detail: str = Field(description="Why it is a risk and how to fix it")
    file: str | None = None
    line: int | None = None
    cwe: str | None = Field(None, description="CWE id, e.g. `CWE-89`", examples=["CWE-89"])


class SecurityReport(BaseModel):
    risk: Literal["none", "low", "medium", "high", "critical"] = Field(
        description="Overall risk; never lower than the most severe issue")
    issues: list[SecurityIssue] = Field(description="Vulnerabilities found, most severe first")


class ReviewResult(BaseModel):
    rubric: str
    language: str
    provider: str
    stars: int = Field(ge=0, le=5)
    rating_text: str
    summary: str
    strengths: list[str]
    weaknesses: list[str]
    languages: list[str] = Field(
        default_factory=list, description="Programming languages detected in the code, from rubrics with `input: code`")
    production: ProductionVerdict | None = Field(
        None, description="Whether the code is ready for production, from rubrics with `input: code`")
    security: SecurityReport | None = Field(
        None, description="Security risk and vulnerabilities, from rubrics with `input: code`")
    suggestions: list[CodeSuggestion] = Field(
        default_factory=list, description="Code changes, from rubrics with `input: code`; empty otherwise")


class PassageIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(pattern=r"^[A-Za-z0-9_-]{1,128}$", description="The caller's stable passage id, returned in `citations`")
    source: str = Field(min_length=1, max_length=255, description="Source label, e.g. a file name", examples=["kirjasto.txt"])
    text: str = Field(min_length=1, max_length=2000, description="The passage text; treated as untrusted data")


class GroundedAnswerBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    question: str = Field(min_length=1, max_length=500, examples=["Milloin kampuskirjasto on auki?"])
    language: Literal["fi"] = Field("fi", description="Answer language; only Finnish for now")
    passages: list[PassageIn] = Field(
        default_factory=list, max_length=8, description="Retrieved passages; empty means `no_evidence` without a model call")

    @field_validator("question")
    @classmethod
    def _question_not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("question must not be blank")
        return value.strip()

    @model_validator(mode="after")
    def _unique_ids(self) -> "GroundedAnswerBody":
        ids = [p.id for p in self.passages]
        if len(ids) != len(set(ids)):
            raise ValueError("passage ids must be unique")
        return self


class GroundedAnswerReply(BaseModel):
    status: Literal["answered", "no_evidence"]
    answer: str = Field(description="Finnish answer with `[n]` markers (1-based positions in `citations`), "
                                     "or a fixed sentence for `no_evidence`")
    citations: list[str] = Field(description="Passage ids from the request, in the order the answer cites them")


class ProviderInfo(BaseModel):
    name: str
    configured: bool
    tools: bool
    embeddings: bool


AgentId = Annotated[str, Path(description="Agent id from `GET /v1/agents`", examples=["jussispace"])]


@router.get("/agents", tags=["Agents"], summary="List agents")
async def list_agents(
    request: Request,
    client: Annotated[Client, Depends(require_client(None))],
) -> list[AgentInfo]:
    """Agents this API key or origin may use."""
    svc = services(request)
    return [
        AgentInfo(
            id=config.id,
            name=config.name,
            description=config.description,
            languages=sorted(config.language_instructions),
        )
        for agent_id, config in sorted(svc.agents.configs.items())
        if client.can_use_agent(agent_id)
    ]


@router.post("/agents/{agent_id}/chat", tags=["Agents"], summary="Chat with an agent")
async def agent_chat(
    request: Request,
    agent_id: AgentId,
    body: ChatBody,
    client: Annotated[Client, Depends(require_client("chat"))],
    user_token: UserToken = None,
) -> ChatReply:
    """Send a message (plus earlier messages for multi-turn chat) and get the agent's reply.

    Tools that show a user's own data (such as orders) need that user's backend token
    in the `X-User-Token` header; without it the agent asks the user to sign in.
    """
    svc = services(request)
    if not svc.agents.has(agent_id) or not client.can_use_agent(agent_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Agent '{agent_id}' not found.")
    agent = svc.agents.get(agent_id)
    history = [ChatTurn(role=m.role, content=m.content) for m in body.history]
    reply = await call_ai(
        lambda: agent.chat(body.message, language=body.language, history=history, user_token=user_token or ""),
        error_prefix="Agent error: ",
    )
    return ChatReply(agent=agent_id, reply=reply)


@router.get("/review/rubrics", tags=["Review"], summary="List review rubrics")
async def list_rubrics(
    request: Request,
    client: Annotated[Client, Depends(require_client(None))],
) -> list[RubricInfo]:
    """Rubrics this API key or origin may use with `POST /v1/review`."""
    svc = services(request)
    return [
        RubricInfo(id=r.id, name=r.name, description=r.description, language=r.language, labels=r.labels)
        for r in sorted(svc.rubrics.values(), key=lambda r: r.id)
        if client.can_use_rubric(r.id)
    ]


@router.post("/review", tags=["Review"], summary="Review a document")
async def review(
    request: Request,
    client: Annotated[Client, Depends(require_client("review"))],
    file: Annotated[
        list[UploadFile] | None,
        File(description="PDF, DOC or DOCX. Code rubrics take up to 20 source files: repeat the field. Send this or `text`."),
    ] = None,
    text: Annotated[str | None, Form(description="The document as plain text. Send this or `file`.")] = None,
    rubric: Annotated[str, Form(description="Rubric id from `GET /v1/review/rubrics`")] = "cv-fi",
    provider: Annotated[
        str | None, Form(description="Provider name; defaults to REVIEW_PROVIDER. Needs an API key.")] = None,
    model: Annotated[
        str | None,
        Form(description="Model name; defaults to the provider's default. Needs an API key, "
                         "and must be in REVIEW_MODELS when that is set."),
    ] = None,
) -> ReviewResult:
    """Rate a document from 0 to 5 stars against a rubric, with a summary, strengths and weaknesses.

    Upload a file **or** send the text in the `text` field. Code rubrics (such as `code-review-en`)
    take one or more source files in most programming languages and return `suggestions`:
    the current code and its replacement.
    """
    svc = services(request)
    files = [f for f in file or [] if f.filename]
    has_file = bool(files)
    has_text = bool((text or "").strip())
    if has_file and has_text:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Send either a file or text, not both.")
    if not has_file and not has_text:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Send a file or text to review.")
    selected = svc.rubrics.get(rubric)
    if selected is None or not client.can_use_rubric(rubric):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Rubric '{rubric}' not found.")
    provider = (provider or "").strip()
    model = (model or "").strip()
    if (provider or model) and not client.key_hash and not svc.clients.open_access:
        # Without a key, anyone could run any model on this service's credentials.
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Choosing the provider or model needs an API key.",
        )
    if model and svc.settings.review_models and model not in svc.settings.review_models:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Model '{model}' is not allowed. Use one of: {', '.join(svc.settings.review_models)}.",
        )
    provider_name = provider or svc.settings.review_provider
    if not svc.providers.exists(provider_name):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unknown provider '{provider_name}'. Use one of: {', '.join(svc.providers.names())}.",
        )

    if has_file and selected.input == "code":
        document = await read_code_files(files, svc.settings.max_upload_bytes)
    elif has_file:
        if len(files) > 1:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="This rubric takes one file.")
        document = await read_document(files[0], svc.settings.max_upload_bytes)
    else:
        document = read_text(text or "", selected.input)
    llm = svc.providers.get(provider_name)
    result = await call_ai(lambda: review_document(selected, document, llm, model=model or None))
    return ReviewResult(**result)


@router.post("/grounded-answer", tags=["Grounded answers"], summary="Answer from the given passages")
async def grounded_answer(
    request: Request,
    body: GroundedAnswerBody,
    client: Annotated[Client, Depends(require_client("grounded-answer"))],
) -> GroundedAnswerReply:
    """Write a short Finnish answer using only `passages`, citing them with `[n]` markers.

    `citations` only ever holds ids from the request. When the passages don't answer the
    question, or none are sent, the reply is `no_evidence` with a fixed Finnish sentence.
    Server-to-server only: the client needs `grounded_answer: true` and an API key.
    """
    if not client.grounded_answer:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="This client may not use grounded answers.")
    svc = services(request)
    provider_name = svc.settings.grounded_answer_provider
    provider = svc.providers.get(provider_name) if svc.providers.exists(provider_name) else None
    passages = [Passage(id=p.id, source=p.source, text=p.text) for p in body.passages]
    result = await call_ai(lambda: answer_from_passages(body.question, passages, provider, client_id=client.id))
    return GroundedAnswerReply(**result)


@router.get("/providers", tags=["Providers"], summary="List AI providers")
async def list_providers(
    request: Request,
    client: Annotated[Client, Depends(require_client(None))],
) -> list[ProviderInfo]:
    """Which providers have credentials set. Useful for checking a deployment."""
    svc = services(request)
    result = []
    for name in svc.providers.names():
        provider = svc.providers.get(name)
        result.append(ProviderInfo(
            name=name,
            configured=provider.is_configured(),
            tools=provider.supports_tools,
            embeddings=provider.supports_embeddings,
        ))
    return result
