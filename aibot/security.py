"""
API clients, authentication and rate limits.

Each client gets its own API key and/or browser origins, the agents and rubrics
it may use, and its own rate limit. Clients come from `config/clients.yaml`
(or `CLIENTS_FILE`). Without that file, the old single-key settings are used:
`AI_SECRET_KEY` and `ALLOWED_ORIGINS`. With neither, everything is open (local dev).
"""
import hashlib
import hmac
import logging
import time
from dataclasses import dataclass
from pathlib import Path

from fastapi import HTTPException, Request, status
from limits import parse
from limits.storage import MemoryStorage
from limits.strategies import MovingWindowRateLimiter
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from aibot.configfile import load_yaml
from aibot.settings import Settings

# Uvicorn's logger, so messages show up in the server log without extra setup.
logger = logging.getLogger("uvicorn.error")


def hash_key(key: str) -> str:
    """SHA-256 hex digest of an API key."""
    return hashlib.sha256(key.encode()).hexdigest()


class ClientConfig(BaseModel):
    """One entry in `clients.yaml`."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$")
    key: str = ""
    key_sha256: str = Field("", pattern=r"^([0-9a-f]{64})?$")
    origins: list[str] = Field(default_factory=list)
    agents: list[str] = Field(default_factory=lambda: ["*"])
    rubrics: list[str] = Field(default_factory=lambda: ["*"])
    rate_limit: str = ""


@dataclass(frozen=True)
class Client:
    """An authenticated caller."""

    id: str
    key_hash: str = ""
    origins: frozenset[str] = frozenset()
    agents: frozenset[str] = frozenset({"*"})
    rubrics: frozenset[str] = frozenset({"*"})
    rate_limit: str = ""

    def can_use_agent(self, agent_id: str) -> bool:
        return "*" in self.agents or agent_id in self.agents

    def can_use_rubric(self, rubric_id: str) -> bool:
        return "*" in self.rubrics or rubric_id in self.rubrics


ANONYMOUS = Client(id="anonymous")


def _normalize_origin(origin: str) -> str:
    return origin.strip().rstrip("/")


def load_clients_file(path: Path) -> list[Client]:
    """Parse `clients.yaml`."""
    data = load_yaml(path)
    clients = []
    for entry in data.get("clients", []) if isinstance(data, dict) else []:
        try:
            config = ClientConfig.model_validate(entry)
        except ValidationError as exc:
            raise ValueError(f"Invalid client in {path.name}:\n{exc}") from exc
        key_hash = config.key_sha256 or (hash_key(config.key) if config.key else "")
        if config.rate_limit:
            parse(config.rate_limit)
        if not key_hash and not config.origins:
            raise ValueError(f"Client '{config.id}' in {path.name} needs a key, key_sha256 or origins.")
        clients.append(Client(
            id=config.id,
            key_hash=key_hash,
            origins=frozenset(_normalize_origin(o) for o in config.origins),
            agents=frozenset(config.agents),
            rubrics=frozenset(config.rubrics),
            rate_limit=config.rate_limit,
        ))
    ids = [client.id for client in clients]
    if len(ids) != len(set(ids)):
        raise ValueError(f"Duplicate client ids in {path.name}.")
    return clients


class ClientRegistry:
    """Resolves the client making a request."""

    def __init__(self, clients: list[Client]) -> None:
        self.clients = clients

    @classmethod
    def from_settings(cls, settings: Settings) -> "ClientRegistry":
        if settings.clients_file is not None:
            return cls(load_clients_file(settings.clients_file))
        if settings.ai_secret_key or settings.allowed_origins:
            return cls([Client(
                id="default",
                key_hash=hash_key(settings.ai_secret_key) if settings.ai_secret_key else "",
                origins=frozenset(settings.allowed_origins),
            )])
        return cls([])

    @property
    def open_access(self) -> bool:
        """True when no clients are configured (local development)."""
        return not self.clients

    def cors_origins(self) -> list[str]:
        """All origins any client may call from."""
        return sorted({origin for client in self.clients for origin in client.origins})

    def resolve(self, request: Request) -> Client:
        """Identify the caller, or raise 401/403.

        - A bearer key identifies its client. If that client lists origins and the
          request has an `Origin` header, the origin must be one of them.
        - Without a key, the `Origin` must belong to a client that has no key
          (a browser-only client).
        """
        if self.open_access:
            return ANONYMOUS

        origin = _normalize_origin(request.headers.get("origin", ""))
        auth_header = request.headers.get("authorization", "")

        if auth_header:
            if not auth_header.startswith("Bearer "):
                raise _unauthorized("Missing or invalid Authorization header. Expected: Bearer <key>")
            provided = hash_key(auth_header.removeprefix("Bearer ").strip())
            client = next(
                (c for c in self.clients if c.key_hash and hmac.compare_digest(c.key_hash, provided)),
                None,
            )
            if client is None:
                raise _unauthorized("Invalid key.")
            if origin and client.origins and origin not in client.origins:
                raise _forbidden()
            return client

        if origin:
            for client in self.clients:
                if not client.key_hash and origin in client.origins:
                    return client
            if any(origin in client.origins for client in self.clients):
                raise _unauthorized("Missing or invalid Authorization header. Expected: Bearer <key>")
            raise _forbidden()

        raise _unauthorized("Missing or invalid Authorization header. Expected: Bearer <key>")


def _unauthorized(detail: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=detail,
        headers={"WWW-Authenticate": "Bearer"},
    )


def _forbidden() -> HTTPException:
    return HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied: origin not allowed.")


class RateLimiter:
    """In-memory moving-window limits per client, client IP and endpoint group."""

    def __init__(self, default_limit: str, forwarded_ip_depth: int = 0, log_forwarded_for: bool = False) -> None:
        parse(default_limit)  # fail fast on an invalid DAILY_RATE_LIMIT
        self.default_limit = default_limit
        self.forwarded_ip_depth = forwarded_ip_depth
        self.log_forwarded_for = log_forwarded_for
        self._limiter = MovingWindowRateLimiter(MemoryStorage())

    def client_ip(self, request: Request) -> str:
        """The caller's IP address.

        With `forwarded_ip_depth` N > 0, the Nth address from the right of
        `X-Forwarded-For` is used: the one added by the outermost trusted proxy.
        Set LOG_FORWARDED_FOR=true to log the header and find the right depth.
        """
        if self.log_forwarded_for:
            logger.info(
                "Client IP check: peer=%s x-forwarded-for=%r",
                request.client.host if request.client else None,
                request.headers.get("x-forwarded-for"),
            )
        if self.forwarded_ip_depth > 0:
            forwarded = [p.strip() for p in request.headers.get("x-forwarded-for", "").split(",") if p.strip()]
            if len(forwarded) >= self.forwarded_ip_depth:
                return forwarded[-self.forwarded_ip_depth]
        return request.client.host if request.client else "unknown"

    def hit(self, request: Request, client: Client, scope: str) -> None:
        """Count one request, or raise 429 when the limit is exceeded."""
        limit = parse(client.rate_limit or self.default_limit)
        identifiers = (client.id, self.client_ip(request), scope)
        if not self._limiter.hit(limit, *identifiers):
            reset_at = self._limiter.get_window_stats(limit, *identifiers).reset_time
            retry_after = max(1, int(reset_at - time.time()))
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Rate limit exceeded: {limit}",
                headers={"Retry-After": str(retry_after)},
            )
