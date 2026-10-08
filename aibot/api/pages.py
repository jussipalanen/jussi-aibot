"""
Root page, health check, version and robots.txt.
"""
import html
import platform
import sys

import fastapi
from fastapi import APIRouter, Request, Response
from fastapi.responses import HTMLResponse, JSONResponse

from aibot import __version__
from aibot.api.deps import services

router = APIRouter(tags=["Service"])

_ROOT_PAGE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex, nofollow">
<title>{name}</title>
<style>
  :root {{
    --bg: #f6f7fb; --card: #ffffff; --text: #1d2433; --muted: #5b6475;
    --accent: #3b5bdb; --accent-text: #ffffff; --border: #e3e6ef;
  }}
  @media (prefers-color-scheme: dark) {{
    :root {{
      --bg: #0f131c; --card: #171c28; --text: #e7eaf2; --muted: #a0a8ba;
      --accent: #748ffc; --accent-text: #0f131c; --border: #262d3d;
    }}
  }}
  * {{ box-sizing: border-box; }}
  body {{
    margin: 0; min-height: 100vh; display: grid; place-items: center; padding: 24px 16px;
    background: var(--bg); color: var(--text);
    font: 16px/1.6 system-ui, -apple-system, "Segoe UI", Roboto, sans-serif;
  }}
  main {{
    width: 100%; max-width: 560px; background: var(--card); border: 1px solid var(--border);
    border-radius: 16px; padding: 40px 32px; text-align: center;
  }}
  .logo {{ display: inline-flex; align-items: center; gap: 12px; margin-bottom: 16px; }}
  .mark {{
    display: grid; place-items: center; width: 48px; height: 48px; border-radius: 12px;
    background: var(--accent); color: var(--accent-text); font-weight: 800; font-size: 20px;
  }}
  .wordmark {{ font-size: 28px; font-weight: 800; letter-spacing: -0.02em; }}
  p {{ color: var(--muted); margin: 0 0 28px; }}
  nav {{ display: flex; flex-wrap: wrap; gap: 12px; justify-content: center; }}
  a {{
    display: inline-block; padding: 10px 18px; border-radius: 10px; text-decoration: none;
    border: 1px solid var(--border); color: var(--text); font-weight: 600;
  }}
  a.primary {{ background: var(--accent); border-color: var(--accent); color: var(--accent-text); }}
  a:hover {{ border-color: var(--accent); }}
  footer {{ margin-top: 28px; font-size: 13px; color: var(--muted); }}
</style>
</head>
<body>
<main>
  <div class="logo" aria-label="{name}">
    <span class="mark" aria-hidden="true">AI</span>
    <span class="wordmark">{name}</span>
  </div>
  <p>{description}</p>
  <nav>
    <a class="primary" href="/docs">API documentation</a>
    <a href="/redoc">ReDoc</a>
    <a href="/openapi.json">OpenAPI JSON</a>
  </nav>
  <footer>Version {version} · <a href="/health" style="padding:0;border:0;font-weight:400">Status</a></footer>
</main>
</body>
</html>
"""


@router.get("/", summary="Service home", response_class=HTMLResponse)
async def root(request: Request) -> Response:
    """A small home page with links to the documentation. Returns JSON when the client asks for it."""
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
        })
    return HTMLResponse(_ROOT_PAGE.format(
        name=html.escape(settings.app_name),
        description=html.escape(settings.app_description),
        version=html.escape(__version__),
    ))


@router.get("/robots.txt", include_in_schema=False)
async def robots_txt() -> Response:
    """Disallow all crawlers."""
    return Response(content="User-agent: *\nDisallow: /\n", media_type="text/plain")


@router.get("/health", summary="Health check")
async def health() -> dict[str, str]:
    """Returns `ok` when the service is running. Makes no AI calls."""
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
