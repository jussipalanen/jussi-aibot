"""
Home page, review demos, health check, version and robots.txt.
"""
import html
import json
import platform
import sys
from pathlib import Path

import fastapi
from fastapi import APIRouter, HTTPException, Request, Response, status
from fastapi.responses import HTMLResponse, JSONResponse

from aibot import __version__
from aibot.api.deps import MAX_CODE_FILES, MAX_TEXT_CHARS, InputKind, services
from aibot.review import languages

router = APIRouter(tags=["Service"])

WEB_DIR = Path(__file__).resolve().parent.parent / "web"
_TEMPLATES = {name: (WEB_DIR / "templates" / f"{name}.html").read_text(encoding="utf-8") for name in ("index", "review")}

_DEMO_LINKS = """<section>
    <h2>Demos</h2>
    <a class="demo-link" href="/demo/review">
      <svg class="icon" width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
        <path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z"/><path d="M14 3v5h5"/><path d="m12 11.5 1.1 2.2 2.4.3-1.8 1.7.5 2.4-2.2-1.2-2.2 1.2.5-2.4-1.8-1.7 2.4-.3z"/>
      </svg>
      <div><strong>CV &amp; application review</strong><span>Upload a CV or job application and get a 0–5 star review.</span></div>
      <span class="arrow" aria-hidden="true">&rarr;</span>
    </a>
    <a class="demo-link" href="/demo/code-review">
      <svg class="icon" width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
        <path d="m8 7-5 5 5 5"/><path d="m16 7 5 5-5 5"/><path d="m14 4-4 16"/>
      </svg>
      <div><strong>Code review</strong><span>Upload source files in most programming languages and get a review with suggested code changes.</span></div>
      <span class="arrow" aria-hidden="true">&rarr;</span>
    </a>
  </section>"""

# The two demo pages share one template and script; `page` picks the rubrics and texts.
_DEMO_PAGES: dict[InputKind, dict[str, str]] = {
    "document": {
        "title": "CV &amp; application review",
        "lead": "Upload a CV or job application, or paste its text. The AI rates it from 0 to 5 stars and lists its strengths and what to improve.",
    },
    "code": {
        "title": "Code review",
        "lead": "Upload source files or paste code. The language is detected automatically, and the AI rates the code from 0 to 5 stars and suggests changes: what to replace and what to use instead.",
    },
}


def _render(template: str, **values: str) -> str:
    """Fill `{{name}}` placeholders. Values must already be HTML-safe."""
    page = _TEMPLATES[template]
    for key, value in values.items():
        page = page.replace("{{" + key + "}}", value)
    return page


@router.get("/", summary="Service home", response_class=HTMLResponse)
async def root(request: Request) -> Response:
    """A small home page with links to the demos and documentation. Returns JSON when the client asks for it."""
    settings = services(request).settings
    accept = request.headers.get("accept", "")
    if "application/json" in accept and "text/html" not in accept:
        return JSONResponse({
            "name": settings.app_name,
            "description": settings.app_description,
            "version": __version__,
            "docs": "/docs",
            "redoc": "/redoc",
            "openapi": "/openapi.json",
            "demos": ["/demo/review", "/demo/code-review"] if settings.demo_enabled else [],
        })
    return HTMLResponse(_render(
        "index",
        name=html.escape(settings.app_name),
        description=html.escape(settings.app_description),
        version=html.escape(__version__),
        demos=_DEMO_LINKS if settings.demo_enabled else "",
        docs_class="" if settings.demo_enabled else "primary",
    ))


def _demo_page(request: Request, page: InputKind) -> Response:
    """A review form for the rubrics of one input kind: documents or code."""
    svc = services(request)
    settings = svc.settings
    if not settings.demo_enabled:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not Found")

    config = {
        "page": page,
        "appName": settings.app_name,
        "maxUploadMb": settings.max_upload_bytes // (1024 * 1024),
        "maxTextChars": MAX_TEXT_CHARS,
        "rubrics": [
            {"id": r.id, "name": r.name, "language": r.language}
            for r in sorted(svc.rubrics.values(), key=lambda r: r.id)
            if r.input == page
        ],
    }
    if page == "code":
        config |= {"maxCodeFiles": MAX_CODE_FILES, **languages.browser_config()}
    texts = _DEMO_PAGES[page]
    return HTMLResponse(_render(
        "review",
        name=html.escape(settings.app_name),
        title=texts["title"],
        lead=texts["lead"],
        max_chars=str(MAX_TEXT_CHARS),
        config=json.dumps(config).replace("<", "\\u003c"),
    ))


@router.get("/demo/review", include_in_schema=False)
async def review_demo(request: Request) -> Response:
    """A form for trying CV and application reviews (`POST /v1/review`) in the browser."""
    return _demo_page(request, "document")


@router.get("/demo/code-review", include_in_schema=False)
async def code_review_demo(request: Request) -> Response:
    """A form for trying code reviews in the browser: several source files or pasted code."""
    return _demo_page(request, "code")


@router.get("/robots.txt", include_in_schema=False)
async def robots_txt() -> Response:
    """Disallow all crawlers."""
    return Response(content="User-agent: *\nDisallow: /\n", media_type="text/plain")


@router.get("/health", summary="Health check")
@router.head("/health", include_in_schema=False)
async def health() -> dict[str, str]:
    """Returns `ok` when the service is running. Makes no AI calls.

    Also answers `HEAD`, which uptime monitors such as UptimeRobot send by default.
    """
    return {"status": "ok"}


@router.get("/version", summary="Version information")
async def version() -> dict[str, str]:
    """Application, Python and FastAPI versions."""
    try:
        import torch

        torch_version = torch.__version__
    except ImportError:
        torch_version = "N/A (ML dependencies not installed)"

    return {
        "version": __version__,
        "python_version": sys.version.split()[0],
        "platform": platform.platform(),
        "fastapi_version": fastapi.__version__,
        "torch_version": torch_version,
    }
