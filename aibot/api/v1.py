"""
Version 1 of the platform API.
"""
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, File, Form, HTTPException, Path, Request, UploadFile, status
from pydantic import BaseModel, Field

from aibot.agents.engine import ChatTurn
from aibot.api.deps import call_ai, read_document, read_text, require_client, services
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
    content: str


class ChatBody(BaseModel):
    message: str = Field(min_length=1, max_length=8000, examples=["Näytä vapaat asunnot Helsingissä"])
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


class ReviewResult(BaseModel):
    rubric: str
    language: str
    provider: str
    stars: int = Field(ge=0, le=5)
    rating_text: str
    summary: str
    strengths: list[str]
    weaknesses: list[str]


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
) -> ChatReply:
    """Send a message (plus earlier messages for multi-turn chat) and get the agent's reply."""
    svc = services(request)
    if not svc.agents.has(agent_id) or not client.can_use_agent(agent_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Agent '{agent_id}' not found.")
    agent = svc.agents.get(agent_id)
    history = [ChatTurn(role=m.role, content=m.content) for m in body.history]
    reply = await call_ai(
        lambda: agent.chat(body.message, language=body.language, history=history),
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
    file: Annotated[UploadFile | None, File(description="PDF, DOC or DOCX. Send this or `text`.")] = None,
    text: Annotated[str | None, Form(description="The document as plain text. Send this or `file`.")] = None,
    rubric: Annotated[str, Form(description="Rubric id from `GET /v1/review/rubrics`")] = "cv-fi",
    provider: Annotated[str | None, Form(description="Provider name; defaults to REVIEW_PROVIDER")] = None,
    model: Annotated[str | None, Form(description="Model name; defaults to the provider's default")] = None,
) -> ReviewResult:
    """Rate a document from 0 to 5 stars against a rubric, with a summary, strengths and weaknesses.

    Upload a file **or** send the text in the `text` field.
    """
    svc = services(request)
    has_file = file is not None and bool(file.filename)
    has_text = bool((text or "").strip())
    if has_file and has_text:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Send either a file or text, not both.")
    if not has_file and not has_text:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Send a file or text to review.")
    selected = svc.rubrics.get(rubric)
    if selected is None or not client.can_use_rubric(rubric):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Rubric '{rubric}' not found.")
    provider_name = (provider or "").strip() or svc.settings.review_provider
    if not svc.providers.exists(provider_name):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unknown provider '{provider_name}'. Use one of: {', '.join(svc.providers.names())}.",
        )

    if has_file:
        document = await read_document(file, svc.settings.max_upload_bytes)
    else:
        document = read_text(text or "")
    llm = svc.providers.get(provider_name)
    result = await call_ai(lambda: review_document(selected, document, llm, model=(model or "").strip() or None))
    return ReviewResult(**result)


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
