"""
Context sources: JSON fetched from a URL and rendered into the system prompt.
"""
import asyncio
import logging
import time

import httpx

from aibot.agents.config import ContextConfig
from aibot.knowledge.render import render_data, resolve_asset_urls

logger = logging.getLogger(__name__)


class SourceUnavailable(RuntimeError):
    """The source has no URL or could not be fetched (maps to HTTP 503)."""


class ContextSource:
    """Fetches, renders and caches one context source."""

    def __init__(self, config: ContextConfig) -> None:
        self.config = config
        self._text = ""
        self._fetched_at = 0.0
        self._lock = asyncio.Lock()

    async def text(self, http: httpx.AsyncClient) -> str:
        """Rendered text, refreshed when older than the configured TTL."""
        async with self._lock:
            if self._text and time.monotonic() - self._fetched_at < self.config.ttl:
                return self._text
            try:
                self._text = await self._fetch(http)
                self._fetched_at = time.monotonic()
            except (httpx.HTTPError, ValueError) as exc:
                if not self._text:
                    raise SourceUnavailable(f"Context source '{self.config.name}' is unavailable.") from exc
                logger.warning("Refreshing context source %s failed, using cached copy: %s", self.config.name, exc)
            return self._text

    async def _fetch(self, http: httpx.AsyncClient) -> str:
        config = self.config
        if not config.url:
            raise SourceUnavailable(f"Context source '{config.name}' has no URL configured.")
        response = await http.get(config.url, headers=config.headers, timeout=10.0)
        response.raise_for_status()
        data = response.json()
        if config.asset_base_url and config.asset_fields:
            data = resolve_asset_urls(data, config.asset_fields, config.asset_base_url)
        return render_data(
            data,
            fields=config.fields,
            exclude=config.exclude,
            max_text_length=config.max_text_length,
        )
