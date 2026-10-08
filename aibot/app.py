"""
Application factory.
"""
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from aibot import __version__
from aibot.agents.registry import AgentRegistry
from aibot.api import legacy, pages, v1
from aibot.api.pages import WEB_DIR
from aibot.api.deps import Services
from aibot.llm import ProviderRegistry
from aibot.review.rubrics import load_rubrics
from aibot.security import ClientRegistry, RateLimiter
from aibot.settings import Settings

OPENAPI_TAGS = [
    {"name": "Agents", "description": "Chat agents defined in `config/agents/*.yaml`."},
    {"name": "Review", "description": "Document reviews against rubrics in `config/rubrics/*.yaml`."},
    {"name": "Providers", "description": "Configured AI providers."},
    {"name": "Service", "description": "Home page, health and version."},
    {"name": "Legacy", "description": "Original endpoints, kept for existing frontends. Prefer `/v1`."},
]

API_DESCRIPTION = """
{description}

**Authentication:** send `Authorization: Bearer <key>` from servers. Browser
clients listed in the clients config are identified by their `Origin` instead.
Local development without any clients configured needs no authentication.

**Rate limits:** per client, per IP address, for chat and review separately.
Exceeding a limit returns `429` with a `Retry-After` header.
"""


class _HttpClient:
    """One shared `httpx.AsyncClient`, created on first use."""

    def __init__(self) -> None:
        self._client: httpx.AsyncClient | None = None

    def __call__(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(timeout=httpx.Timeout(15.0, connect=5.0))
        return self._client

    async def aclose(self) -> None:
        if self._client is not None:
            await self._client.aclose()


def create_app(settings: Settings | None = None, providers: ProviderRegistry | None = None) -> FastAPI:
    """Build the FastAPI app. Config files are validated here; no AI calls are made."""
    settings = settings or Settings.from_env()
    providers = providers or ProviderRegistry()
    http = _HttpClient()
    agents = AgentRegistry(AgentRegistry.load_configs(settings.config_dir / "agents"), providers, http)
    clients = ClientRegistry.from_settings(settings)

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        yield
        await providers.aclose()
        await http.aclose()

    app = FastAPI(
        title=settings.app_name,
        version=__version__,
        description=API_DESCRIPTION.format(description=settings.app_description),
        openapi_tags=OPENAPI_TAGS,
        lifespan=lifespan,
    )
    app.state.services = Services(
        settings=settings,
        providers=providers,
        agents=agents,
        rubrics=load_rubrics(settings.config_dir / "rubrics"),
        clients=clients,
        limiter=RateLimiter(settings.default_rate_limit, settings.forwarded_ip_depth, settings.log_forwarded_for),
        http=http,
    )

    # Without any configured origins (local dev or key-only clients), allow all:
    # requests still need a valid key when keys are configured.
    origins = clients.cors_origins()
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins or ["*"],
        allow_credentials=bool(origins),
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["*"],
    )

    @app.middleware("http")
    async def add_robots_header(request: Request, call_next) -> Response:
        """Ask search engines not to index any response."""
        response = await call_next(request)
        response.headers["X-Robots-Tag"] = "noindex, nofollow, noarchive, nosnippet"
        return response

    app.mount("/static", StaticFiles(directory=WEB_DIR / "static"), name="static")
    app.include_router(pages.router)
    app.include_router(v1.router)
    app.include_router(legacy.router)
    return app
