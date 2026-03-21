import os
import requests

BASE_URL = os.environ["JUSSISPACE_API_URL"]  # e.g. https://api.jussispace.com/api


class JussispaceClient:
    def __init__(self):
        self._token = None

    def _get_token(self):
        if self._token:
            return self._token
        res = requests.post(f"{BASE_URL}/auth/login", json={
            "email":    os.environ["AGENT_EMAIL"],
            "password": os.environ["AGENT_PASSWORD"],
        })
        res.raise_for_status()
        self._token = res.json()["token"]
        return self._token

    def _headers(self):
        return {"Authorization": f"Bearer {self._get_token()}"}

    def call_tool(self, name: str, args: dict):
        if name == "search_properties":
            return requests.get(f"{BASE_URL}/properties", params=args).json()

        if name == "get_property":
            return requests.get(f"{BASE_URL}/properties/{args['id']}").json()

        if name == "get_order_status":
            return requests.get(f"{BASE_URL}/orders/{args['id']}", headers=self._headers()).json()

        if name == "list_orders":
            return requests.get(f"{BASE_URL}/orders", params=args, headers=self._headers()).json()

        return {"error": f"Unknown tool: {name}"}
