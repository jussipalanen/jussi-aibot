"""
Shared request dependencies and error mapping.
"""
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Literal, TypeVar

import httpx
from fastapi import Depends, HTTPException, Request, UploadFile, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from starlette.concurrency import run_in_threadpool

from aibot.agents.engine import AgentUnavailable
from aibot.agents.registry import AgentRegistry
from aibot.knowledge.sources import SourceUnavailable
from aibot.llm import ProviderError, ProviderNotConfigured, ProviderRegistry
from aibot.review.extract import (
    ALLOWED_EXTENSIONS,
    UnsupportedDocument,
    clean_filename,
    extract_code_text,
    extract_document_text,
    file_header,
    is_code_file,
    normalize_code,
    normalize_whitespace,
)
from aibot.review.rubrics import Rubric
from aibot.security import Client, ClientRegistry, RateLimiter
from aibot.settings import Settings

T = TypeVar("T")

MAX_TEXT_CHARS = 100_000

MAX_CODE_FILES = 20

InputKind = Literal["document", "code"]


@dataclass
class Services:
    """Everything the routes need, stored on `app.state.services`."""

    settings: Settings
    providers: ProviderRegistry
    agents: AgentRegistry
    rubrics: dict[str, Rubric]
    clients: ClientRegistry
    limiter: RateLimiter
    http: Callable[[], httpx.AsyncClient]


def services(request: Request) -> Services:
    return request.app.state.services


# Declares bearer auth in the OpenAPI schema (the "Authorize" button in /docs).
# The key itself is checked by ClientRegistry.resolve.
bearer_scheme = HTTPBearer(auto_error=False, description="API key of a client")


def require_client(scope: str | None) -> Callable[..., Client]:
    """Dependency that authenticates the caller and, with a scope, counts a request."""
    def dependency(
        request: Request,
        _: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    ) -> Client:
        svc = services(request)
        client = svc.clients.resolve(request)
        if scope:
            svc.limiter.hit(request, client, scope)
        return client

    return dependency


async def call_ai(func: Callable[[], Awaitable[T]], *, error_prefix: str = "") -> T:
    """Run an AI call and map failures to HTTP errors (503 not configured, 502 failed)."""
    try:
        return await func()
    except HTTPException:
        raise
    except (ProviderNotConfigured, AgentUnavailable, SourceUnavailable) as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc
    except ProviderError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"{error_prefix}{exc}") from exc


async def read_document(file: UploadFile, max_bytes: int) -> str:
    """Validate an upload and return its normalized text."""
    if not file.filename:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="File name is required.")
    extension = "." + file.filename.lower().rsplit(".", 1)[-1] if "." in file.filename else ""
    if extension not in ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unsupported file type.")

    file_bytes = await file.read(max_bytes + 1)
    if len(file_bytes) > max_bytes:
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail=f"File too large. Max size is {max_bytes // (1024 * 1024)}MB.",
        )

    try:
        text = await run_in_threadpool(extract_document_text, file_bytes, file.filename)
    except UnsupportedDocument as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    text = normalize_whitespace(text)
    if not text:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No text could be extracted from the uploaded file.",
        )
    return text


async def read_code_files(files: list[UploadFile], max_bytes: int) -> str:
    """Validate source file uploads and join them, each under a `==> name <==` header."""
    if len(files) > MAX_CODE_FILES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Too many files. Send at most {MAX_CODE_FILES}.",
        )
    parts = []
    total = 0
    for file in files:
        name = clean_filename(file.filename or "")
        if not name or not is_code_file(name):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Unsupported file type: '{name}'. Upload source code files.",
            )
        file_bytes = await file.read(max_bytes + 1 - total)
        total += len(file_bytes)
        if total > max_bytes:
            raise HTTPException(
                status_code=status.HTTP_413_CONTENT_TOO_LARGE,
                detail=f"Files too large. Max total size is {max_bytes // (1024 * 1024)}MB.",
            )
        try:
            code = normalize_code(extract_code_text(file_bytes))
        except UnsupportedDocument as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"{name}: {exc}") from exc
        if code:
            parts.append(file_header(name) + "\n" + code)
    if not parts:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="The uploaded files are empty.")
    return "\n\n".join(parts)


def read_text(text: str, input_kind: InputKind = "document") -> str:
    """Validate pasted document text or code and return it normalized."""
    if len(text) > MAX_TEXT_CHARS:
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail=f"Text too long. Max length is {MAX_TEXT_CHARS} characters.",
        )
    return normalize_code(text) if input_kind == "code" else normalize_whitespace(text)
