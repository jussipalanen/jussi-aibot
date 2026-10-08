"""
The original `/ai/chat` and `/ai/review` endpoints, kept for existing frontends.
New integrations should use the `/v1` endpoints.
"""
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile, status
from pydantic import BaseModel, Field

from aibot.agents.engine import ChatTurn
from aibot.api.deps import call_ai, read_document, require_client, services
from aibot.llm import Message, ProviderRegistry
from aibot.review import cv_fi
from aibot.security import Client
from aibot.settings import LEGACY_REVIEW_PROVIDERS

router = APIRouter(tags=["Legacy"])


class ChatHistoryMessage(BaseModel):
    """A single message in a multi-turn chat history."""

    role: str = Field(description='"user" or "assistant"')
    content: str


class ChatRequest(BaseModel):
    """Request body for `/ai/chat`."""

    handler: str = Field(description="Agent id, e.g. `jussispace`", examples=["jussispace"])
    message: str
    language: str | None = Field(None, description='"fi" or "en"; mirrors the user when omitted')
    history: list[ChatHistoryMessage] = Field(default_factory=list)


@router.post("/ai/chat", deprecated=True, summary="Chat with an agent (legacy)")
async def chat(
    request: Request,
    body: ChatRequest,
    client: Annotated[Client, Depends(require_client("chat"))],
) -> dict:
    """Same as `POST /v1/agents/{handler}/chat`, with the agent id in the body."""
    svc = services(request)
    if not svc.agents.has(body.handler) or not client.can_use_agent(body.handler):
        allowed = [a for a in svc.agents.ids() if client.can_use_agent(a)]
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unknown handler '{body.handler}'. Supported: {', '.join(allowed)}.",
        )
    agent = svc.agents.get(body.handler)
    history = [ChatTurn(role=m.role, content=m.content) for m in body.history]
    reply = await call_ai(
        lambda: agent.chat(body.message, language=body.language, history=history),
        error_prefix="Agent error: ",
    )
    return {"reply": reply}


@router.post("/ai/review", deprecated=True, summary="Review a Finnish CV (legacy)")
async def ai_review(
    request: Request,
    file: Annotated[UploadFile, File(description="PDF, DOC or DOCX")],
    client: Annotated[Client, Depends(require_client("review"))],
    provider: Annotated[str | None, Form(description="default, puter_ai or vertex_ai")] = None,
) -> dict:
    """Finnish CV review with the original response format. See `POST /v1/review` for other rubrics."""
    svc = services(request)
    settings = svc.settings
    provider = (provider or "").strip().lower() or settings.legacy_review_provider
    if provider not in LEGACY_REVIEW_PROVIDERS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid provider. Use one of: {', '.join(sorted(LEGACY_REVIEW_PROVIDERS))}.",
        )

    parsed_text = await read_document(file, settings.max_upload_bytes)

    if ProviderRegistry.normalize(provider) == "gemini":
        limit = settings.legacy_vertex_prompt_max_chars
        prompt = cv_fi.VERTEX_REVIEW_PROMPT_TEMPLATE.format(resume_text=parsed_text[:limit] if limit > 0 else parsed_text)
        json_output = True
    elif provider == "puter_ai":
        limit = settings.legacy_puter_prompt_max_chars
        prompt = cv_fi.REVIEW_PROMPT_TEMPLATE.format(resume_text=parsed_text[:limit] if limit > 0 else parsed_text)
        json_output = False
    else:
        prompt = cv_fi.REVIEW_PROMPT_TEMPLATE.format(resume_text=parsed_text)
        json_output = False

    llm = svc.providers.get(provider)
    response = await call_ai(lambda: llm.generate([Message(role="user", content=prompt)], json_output=json_output))
    return cv_fi.build_review_response(parsed_text, response.text, provider=provider)
