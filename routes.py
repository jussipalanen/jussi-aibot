"""
API routes for Jussi AI Bot.
"""
from fastapi import APIRouter, File, UploadFile, HTTPException, status, Request, Response, Form
from pydantic import BaseModel
from slowapi import Limiter
from slowapi.util import get_remote_address
import sys
import platform
import fastapi
import os

from services import (
    extract_resume_text,
    normalize_whitespace,
    build_review_response,
    generate_review_default,
    generate_review_puter_ai,
    generate_review_vertex_ai
)

# Constants
ALLOWED_EXTENSIONS = {".pdf", ".doc", ".docs", ".docx"}
MAX_UPLOAD_BYTES = 50 * 1024 * 1024
SUPPORTED_PROVIDERS = {"default", "puter_ai", "vertex_ai"}
DEFAULT_PROVIDER = os.getenv("DEFAULT_PROVIDER", "default").strip().lower()
DAILY_RATE_LIMIT = os.getenv("DAILY_RATE_LIMIT", "50/day")
PUTER_PROMPT_MAX_CHARS = int(os.getenv("PUTER_PROMPT_MAX_CHARS", "6000"))
VERTEX_PROMPT_MAX_CHARS = int(os.getenv("VERTEX_PROMPT_MAX_CHARS", "6000"))

# Validate DEFAULT_PROVIDER at startup
if DEFAULT_PROVIDER not in SUPPORTED_PROVIDERS:
    raise ValueError(
        f"Invalid DEFAULT_PROVIDER '{DEFAULT_PROVIDER}'. "
        f"Must be one of: {', '.join(sorted(SUPPORTED_PROVIDERS))}"
    )

# Rate limiter setup
limiter = Limiter(key_func=get_remote_address)



# Review prompt template (completion-style for local/puter providers)
REVIEW_PROMPT_TEMPLATE = (
    "Ansioluettelo:\n{resume_text}\n\n"
    "Arvostelu: Tämä on"
)

# Structured prompt for Vertex AI (Gemini) — deep analysis with explicit criteria
VERTEX_REVIEW_PROMPT_TEMPLATE = (
    "Olet kokenut rekrytoija ja ansioluettelon arvioija. Analysoi seuraava ansioluettelo perusteellisesti "
    "ja arvioi jokainen alla oleva kriteeri erikseen.\n\n"
    "Arviointikriteerit:\n"
    "1. Yhteystiedot — nimi, sähköposti, puhelin, LinkedIn/portfolio\n"
    "2. Ammatillinen tiivistelmä tai profiili — onko selkeä ja houkutteleva\n"
    "3. Työkokemus — työnimikkeet, työnantajat, päivämäärät, vastuut ja saavutukset\n"
    "4. Koulutus — tutkinnot, oppilaitokset, valmistumisvuodet\n"
    "5. Taidot ja osaaminen — tekniset taidot, kielet, sertifikaatit\n"
    "6. Saavutukset — mitattavat tulokset, luvut, prosentit\n"
    "7. Rakenne ja luettavuus — selkeä jäsentely, johdonmukaisuus\n"
    "8. Pituus ja kattavuus — riittävä yksityiskohtaisuus suhteessa kokemukseen\n"
    "9. ATS-yhteensopivuus — selkeät otsikot, ei taulukoita tai erikoismerkkejä\n"
    "10. Kokonaisvaikutelma — erottuuko CV edukseen\n\n"
    "Ansioluettelo:\n{resume_text}\n\n"
    "Palauta vastauksesi AINOASTAAN seuraavassa JSON-muodossa ilman muuta tekstiä tai markdown-koodimerkkejä:\n"
    '{{\n'
    '  "stars": <kokonaisluku 0-5>,\n'
    '  "rating_text": "<Erinomainen|Erittäin hyvä|Hyvä|Tyydyttävä|Heikko|Huono>",\n'
    '  "summary": "<kattava yhteenveto suomeksi, 2-4 lausetta>",\n'
    '  "strengths": ["<konkreettinen vahvuus 1>", "<konkreettinen vahvuus 2>", "<konkreettinen vahvuus 3>"],\n'
    '  "weaknesses": ["<kehityskohde 1>", "<kehityskohde 2>", "<kehityskohde 3>"]\n'
    '}}'
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


SUPPORTED_CHAT_HANDLERS = {"jussispace", "jussimatic-ai-cv-chat"}

class ChatHistoryMessage(BaseModel):
    role: str  # "user" or "assistant"
    content: str


class ChatRequest(BaseModel):
    handler: str  # e.g. "jussispace"
    message: str
    language: str | None = None
    history: list[ChatHistoryMessage] = []


@router.post("/ai/chat")
@limiter.limit(DAILY_RATE_LIMIT)
async def chat(request: Request, body: ChatRequest) -> dict:
    """
    Conversational AI agent. Use `handler` to select the chatbot:
    - "jussispace" — searches properties and checks orders
    """
    if body.handler not in SUPPORTED_CHAT_HANDLERS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unknown handler '{body.handler}'. Supported: {', '.join(sorted(SUPPORTED_CHAT_HANDLERS))}."
        )

    try:
        if body.handler == "jussispace":
            from agent.agent import ask
            reply = ask(
                body.message,
                language=body.language,
                history=[m.model_dump() for m in body.history],
            )
        elif body.handler == "jussimatic-ai-cv-chat":
            from agent.jussimatic_cv_agent import ask
            reply = ask(
                body.message,
                language=body.language,
                history=[m.model_dump() for m in body.history],
            )
    except RuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"Agent error: {exc}") from exc

    return {"reply": reply}


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
    
    # Use environment variable if provider not provided
    if provider is None or provider.strip() == "":
        provider = DEFAULT_PROVIDER
    else:
        provider = provider.strip().lower()
    
    if provider not in SUPPORTED_PROVIDERS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid provider. Use one of: {', '.join(sorted(SUPPORTED_PROVIDERS))}."
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
    if provider == "vertex_ai":
        prompt_text = parsed_text[:VERTEX_PROMPT_MAX_CHARS] if VERTEX_PROMPT_MAX_CHARS > 0 else parsed_text
        prompt = VERTEX_REVIEW_PROMPT_TEMPLATE.format(resume_text=prompt_text)
        model_output = generate_review_vertex_ai(prompt)
    elif provider == "puter_ai":
        prompt_text = parsed_text[:PUTER_PROMPT_MAX_CHARS] if PUTER_PROMPT_MAX_CHARS > 0 else parsed_text
        prompt = REVIEW_PROMPT_TEMPLATE.format(resume_text=prompt_text)
        model_output = generate_review_puter_ai(prompt)
    else:
        prompt = REVIEW_PROMPT_TEMPLATE.format(resume_text=parsed_text)
        model_output = generate_review_default(prompt)

    # Build response
    response = build_review_response(parsed_text, model_output, provider=provider)

    return response
