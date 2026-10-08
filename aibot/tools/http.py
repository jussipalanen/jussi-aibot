"""
HTTP tools: call a REST endpoint described in an agent config.

The model only chooses argument values. The host, path and method come from the
config, path values are URL-encoded, and arguments that are not declared in the
tool's JSON Schema are dropped.
"""
import asyncio
import json
import logging
import re
from typing import Any
from urllib.parse import quote

import httpx

from aibot.agents.config import AuthConfig, ToolConfig

logger = logging.getLogger(__name__)

_PATH_PARAM = re.compile(r"\{([A-Za-z_][A-Za-z0-9_]*)\}")


class AuthSession:
    """Holds credentials for one auth profile and refreshes login tokens."""

    def __init__(self, config: AuthConfig) -> None:
        self.config = config
        self._token = ""
        self._lock = asyncio.Lock()

    async def headers(self, http: httpx.AsyncClient) -> dict[str, str]:
        """Headers to send with a request."""
        config = self.config
        if config.type == "bearer":
            return {"Authorization": f"Bearer {config.token}"}
        if config.type == "header":
            return {config.header: config.value}
        if config.type == "login":
            return {"Authorization": f"Bearer {await self._login_token(http)}"}
        return {}

    def invalidate(self) -> None:
        """Forget the login token so the next request logs in again."""
        self._token = ""

    async def _login_token(self, http: httpx.AsyncClient) -> str:
        async with self._lock:
            if not self._token:
                response = await http.post(self.config.login_url, json=self.config.body, timeout=10.0)
                response.raise_for_status()
                token = response.json().get(self.config.token_field)
                if not isinstance(token, str) or not token:
                    raise ValueError(f"login response has no '{self.config.token_field}'")
                self._token = token
            return self._token


class HttpTool:
    """Runs one configured HTTP tool."""

    def __init__(self, config: ToolConfig, auth: AuthSession | None) -> None:
        self.config = config
        self.auth = auth
        self.allowed_args = set(config.parameters.get("properties", {}))

    async def call(self, arguments: dict[str, Any], http: httpx.AsyncClient) -> Any:
        """Call the endpoint and return the decoded JSON (or an error object for the model)."""
        args = {k: v for k, v in arguments.items() if k in self.allowed_args and v is not None}
        try:
            url = self._build_url(args)
        except KeyError as exc:
            return {"error": f"missing required argument: {exc.args[0]}"}

        paginate = self.config.http.paginate
        try:
            if paginate:
                return await self._fetch_all_pages(url, args, http)
            return await self._request(url, args, http)
        except httpx.HTTPError as exc:
            logger.warning("Tool %s failed: %s", self.config.name, exc)
            return {"error": "the backend could not be reached"}
        except ValueError as exc:
            logger.warning("Tool %s failed: %s", self.config.name, exc)
            return {"error": "the backend returned an invalid response"}

    def _build_url(self, args: dict[str, Any]) -> str:
        """Fill `{name}` placeholders, removing those arguments from `args`."""
        def fill(match: re.Match) -> str:
            return quote(str(args.pop(match.group(1))), safe="")

        return _PATH_PARAM.sub(fill, self.config.http.url)

    async def _request(self, url: str, args: dict[str, Any], http: httpx.AsyncClient) -> Any:
        config = self.config.http
        send_as_query = config.method in {"GET", "DELETE"}

        async def send() -> httpx.Response:
            headers = dict(config.headers)
            if self.auth:
                headers.update(await self.auth.headers(http))
            return await http.request(
                config.method,
                url,
                params=args if send_as_query else None,
                json=None if send_as_query else args,
                headers=headers,
                timeout=config.timeout,
            )

        response = await send()
        if response.status_code == 401 and self.auth and self.auth.config.type == "login":
            self.auth.invalidate()
            response = await send()

        if response.status_code >= 400:
            return {"error": f"HTTP {response.status_code}", "detail": _decode(response, 500)}
        return _decode(response)

    async def _fetch_all_pages(self, url: str, args: dict[str, Any], http: httpx.AsyncClient) -> Any:
        paginate = self.config.http.paginate
        params = {k: v for k, v in args.items() if k not in (paginate.page_param, paginate.limit_param)}
        params[paginate.limit_param] = paginate.page_size
        items: list[Any] = []
        page, total_pages = 1, 1
        while page <= min(total_pages, paginate.max_pages):
            result = await self._request(url, {**params, paginate.page_param: page}, http)
            if not isinstance(result, dict) or "error" in result:
                return result
            items.extend(result.get(paginate.data_field) or [])
            try:
                total_pages = int(result.get(paginate.total_pages_field) or 1)
            except (TypeError, ValueError):
                total_pages = 1
            page += 1
        return {paginate.data_field: items, "total": len(items)}


def _decode(response: httpx.Response, limit: int = 0) -> Any:
    """Decode a JSON body, or return (part of) the text."""
    try:
        return response.json()
    except (json.JSONDecodeError, ValueError):
        text = response.text
        return {"text": text[:limit] if limit else text}
