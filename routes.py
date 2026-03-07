"""
API routes for Jussi AI Bot.
"""
from fastapi import APIRouter, File, UploadFile, HTTPException, status, Request, Response, Form
from slowapi import Limiter
from slowapi.util import get_remote_address
import hashlib
import hmac
import sys
import platform
import fastapi
import os

from services import (
    extract_resume_text,
    normalize_whitespace,
    build_review_response,
    generate_review_default,
    generate_review_puter_ai
)

# Constants
ALLOWED_EXTENSIONS = {".pdf", ".doc", ".docs", ".docx"}
MAX_UPLOAD_BYTES = 50 * 1024 * 1024
SUPPORTED_PROVIDERS = {"default", "puter_ai"}
DEFAULT_PROVIDER = os.getenv("DEFAULT_PROVIDER", "default").strip().lower()  # Configurable via env var
DAILY_RATE_LIMIT = os.getenv("DAILY_RATE_LIMIT", "50/day")  # Configurable via env var
PUTER_PROMPT_MAX_CHARS = int(os.getenv("PUTER_PROMPT_MAX_CHARS", "6000"))
API_KEYS = {
    key.strip()
    for key in os.getenv("API_KEYS", "").split(",")
    if key.strip()
}
API_KEY_HASHES = {
    key.strip().lower()
    for key in os.getenv("API_KEY_HASHES", "").split(",")
    if key.strip()
}
REQUIRE_API_KEY = bool(API_KEYS or API_KEY_HASHES)

# Allowed origins for API key bypass (for frontend clients)
ALLOWED_ORIGINS = {
    origin.strip()
    for origin in os.getenv("ALLOWED_ORIGINS", "").split(",")
    if origin.strip()
}

# Validate DEFAULT_PROVIDER at startup
if DEFAULT_PROVIDER not in SUPPORTED_PROVIDERS:
    raise ValueError(
        f"Invalid DEFAULT_PROVIDER '{DEFAULT_PROVIDER}'. "
        f"Must be one of: {', '.join(SUPPORTED_PROVIDERS)}"
    )

# Rate limiter setup
limiter = Limiter(key_func=get_remote_address)


def verify_api_key(request: Request) -> None:
    if not REQUIRE_API_KEY:
        return

    # Check if request is from an allowed origin (frontend bypass)
    if ALLOWED_ORIGINS:
        origin = request.headers.get("origin") or request.headers.get("referer", "")
        if origin:
            # Normalize origin by removing trailing slash and path
            origin_normalized = origin.rstrip("/").split("?")[0]
            # For referer, extract just the origin part (scheme + host + port)
            if "referer" in request.headers and not "origin" in request.headers:
                from urllib.parse import urlparse
                parsed = urlparse(origin_normalized)
                origin_normalized = f"{parsed.scheme}://{parsed.netloc}"
            
            # Check against allowed origins
            for allowed in ALLOWED_ORIGINS:
                allowed_normalized = allowed.rstrip("/")
                if origin_normalized == allowed_normalized or origin_normalized.startswith(allowed_normalized + "/"):
                    return  # Allow access without API key for allowed origins

    api_key = request.headers.get("x-api-key")
    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing API key."
        )

    if API_KEYS:
        for key in API_KEYS:
            if hmac.compare_digest(api_key, key):
                return

    if API_KEY_HASHES:
        candidate_hash = hashlib.sha256(api_key.encode("utf-8")).hexdigest()
        for stored_hash in API_KEY_HASHES:
            if hmac.compare_digest(candidate_hash, stored_hash):
                return

    if API_KEYS or API_KEY_HASHES:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid API key."
        )

# Review prompt template
REVIEW_PROMPT_TEMPLATE = (
    "Ansioluettelo:\n{resume_text}\n\n"
    "Arvostelu: Tämä on"
)

# Create router
router = APIRouter()


@router.get("/")
async def root() -> dict[str, str]:
    """Root endpoint."""
    return {"message": "Hello World from Python and FastAPI! Today is a great day to review some resumes!"}


@router.get("/robots.txt")
async def robots_txt() -> Response:
    content = "User-agent: *\nDisallow: /\n"
    return Response(content=content, media_type="text/plain")


@router.get("/health")
async def health() -> dict[str, str]:
    """Health check endpoint."""
    return {"status": "ok"}


@router.get("/version")
async def version() -> dict[str, str]:
    """Get version information."""
    try:
        import torch
        torch_version = torch.__version__
    except ImportError:
        torch_version = "N/A (ML dependencies not installed)"
    
    return {
        "python_version": sys.version.split()[0],
        "platform": platform.platform(),
        "fastapi_version": fastapi.__version__,
        "torch_version": torch_version,
    }


@router.post("/ai/review")
@limiter.limit(DAILY_RATE_LIMIT)
async def ai_review(
    request: Request,
    provider: str = Form(None),
    file: UploadFile = File(...)
) -> dict:
    """
    Review a resume file and provide analysis with ratings.
    Supports PDF, DOC, and DOCX formats and provider selection.
    """
    verify_api_key(request)
    
    # Use environment variable if provider not provided
    if provider is None or provider.strip() == "":
        provider = DEFAULT_PROVIDER
    else:
        provider = provider.strip().lower()
    
    if provider not in SUPPORTED_PROVIDERS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid provider. Use 'default' or 'puter_ai'."
        )

    # Validate file input and size limits
    if not file.filename:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="File name is required."
        )

    _, ext = os.path.splitext(file.filename.lower())
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Unsupported file type."
        )

    file_bytes = await file.read()
    if len(file_bytes) > MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="File too large. Max size is 50MB."
        )

    parsed_text = normalize_whitespace(extract_resume_text(file_bytes, file.filename))
    if not parsed_text:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No text could be extracted from the uploaded file."
        )

    # Generate review with selected provider
    prompt_text = parsed_text
    if provider == "puter_ai" and PUTER_PROMPT_MAX_CHARS > 0:
        prompt_text = parsed_text[:PUTER_PROMPT_MAX_CHARS]

    prompt = REVIEW_PROMPT_TEMPLATE.format(resume_text=prompt_text)
    if provider == "puter_ai":
        model_output = generate_review_puter_ai(prompt)
    else:
        model_output = generate_review_default(prompt)

    # Build response
    response = build_review_response(parsed_text, model_output, provider=provider)

    return response
