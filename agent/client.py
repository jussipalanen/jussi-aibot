"""
HTTP client for the JussiSpace backend API.
"""
import os
import requests

BASE_URL = os.getenv("JUSSISPACE_API_URL", "https://backend-lab-jussispace.jussialanen.com/api")
_TIMEOUT = 10  # seconds


class JussispaceClient:
    """Authenticated client for the JussiSpace REST API."""

    def __init__(self):
        self._token = None

    def _get_token(self):
        """Return a cached auth token, logging in first if not yet acquired."""
        if self._token:
            return self._token
        res = requests.post(f"{BASE_URL}/auth/login", json={  # nosec B106 - password value comes from env var, not hardcoded
            "email":    os.environ["AGENT_EMAIL"],
            "password": os.environ["AGENT_PASSWORD"],
        }, timeout=_TIMEOUT)
        res.raise_for_status()
        self._token = res.json()["token"]
        return self._token

    def _headers(self):
        """Build Authorization headers for authenticated requests."""
        return {"Authorization": f"Bearer {self._get_token()}"}

    def _fetch_all_properties(self, args: dict) -> dict:
        """Fetch all property pages and return them as a single combined list."""
        params = {k: v for k, v in args.items() if k not in ("page", "limit")}
        params["limit"] = 50
        all_data = []
        page = 1
        total_pages = 1
        while page <= total_pages:
            params["page"] = page
            result = requests.get(f"{BASE_URL}/properties", params=params, timeout=_TIMEOUT).json()
            all_data.extend(result.get("data", []))
            total_pages = result.get("totalPages", 1)
            page += 1
        return {"data": all_data, "total": len(all_data)}

    def call_tool(self, name: str, args: dict):
        """Dispatch a tool call by name and return the API response."""
        if name == "search_properties":
            return self._fetch_all_properties(args)

        if name == "get_property":
            return requests.get(f"{BASE_URL}/properties/{args['id']}", timeout=_TIMEOUT).json()

        if name == "get_order_status":
            return requests.get(f"{BASE_URL}/orders/{args['id']}", headers=self._headers(), timeout=_TIMEOUT).json()

        if name == "list_orders":
            return requests.get(f"{BASE_URL}/orders", params=args, headers=self._headers(), timeout=_TIMEOUT).json()

        return {"error": f"Unknown tool: {name}"}
