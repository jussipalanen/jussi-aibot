"""
API routes for Jussi AI Bot.
"""
from fastapi import APIRouter, File, UploadFile, HTTPException, status, Request, Response
from slowapi import Limiter
from slowapi.util import get_remote_address
import hashlib
import hmac
import sys
import platform
import torch
import fastapi
import os

from services import (
    extract_resume_text,
    normalize_whitespace,
    build_review_response
)
from model import model, tokenizer, device

# Constants
ALLOWED_EXTENSIONS = {".pdf", ".doc", ".docs", ".docx"}
MAX_UPLOAD_BYTES = 50 * 1024 * 1024
DAILY_RATE_LIMIT = os.getenv("DAILY_RATE_LIMIT", "50/day")  # Configurable via env var
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

# Rate limiter setup
limiter = Limiter(key_func=get_remote_address)


def verify_api_key(request: Request) -> None:
    if not REQUIRE_API_KEY:
        return

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
    return {"message": "Hello World from Python and FastAPI!"}


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
    return {
        "python_version": sys.version.split()[0],
        "platform": platform.platform(),
        "fastapi_version": fastapi.__version__,
        "torch_version": torch.__version__,
    }


@router.post("/ai/review")
@limiter.limit(DAILY_RATE_LIMIT)
async def ai_review(request: Request, file: UploadFile = File(...)) -> dict:
    """
    Review a resume file and provide analysis with ratings.
    Supports PDF, DOC, and DOCX formats.
    """
    verify_api_key(request)
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

    # Generate review using AI model
    prompt = REVIEW_PROMPT_TEMPLATE.format(resume_text=parsed_text)
    encoded = tokenizer(prompt, return_tensors="pt").to(device)
    input_ids = encoded.input_ids

    outputs = model.generate(
        input_ids,
        max_new_tokens=300,
        temperature=0.8,
        top_p=0.92,
        do_sample=True,
        repetition_penalty=1.1,
        pad_token_id=tokenizer.pad_token_id,
        eos_token_id=tokenizer.eos_token_id
    )

    generated_ids = outputs[0]
    new_tokens = generated_ids[input_ids.shape[-1]:]
    if new_tokens.numel() == 0:
        new_tokens = generated_ids
    model_output = tokenizer.decode(new_tokens, skip_special_tokens=True).strip()

    # Build response
    response = build_review_response(parsed_text, model_output)

    return response
