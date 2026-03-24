import json
import os
import re
import vertexai
from vertexai.generative_models import GenerativeModel
from agent.client import JussispaceClient
from agent.rag import PropertyRAG

_client = JussispaceClient()
_rag = PropertyRAG()

_SUPPORTED_LANGUAGES = {"fi", "en"}

_LANGUAGE_INSTRUCTIONS = {
    "fi": "Vastaa aina suomeksi.",
    "en": "Always respond in English.",
}

_TOOLS_SPEC = """You have access to these tools to fetch real data:

- search_properties: Search for properties.
  Params: city (string), type ("apartment"|"office"), status ("available"|"unavailable"|"maintenance"), page (int), limit (int)

- get_property: Get full details of a property.
  Params: id (int, required)

- get_order_status: Get status and details of an order.
  Params: id (int, required)

- list_orders: List orders.
  Params: userId (int), status ("pending"|"approved"|"declined"|"cancelled"), page (int), limit (int)

RULES:
- Always use tools to fetch real data. Never invent property or order information.
- Respond with ONLY valid JSON — either a tool call or a final answer. No extra text.

To call a tool respond with:
{"type": "tool_call", "tool": "<tool_name>", "params": {<params>}}

To give your final answer respond with:
{"type": "answer", "text": "<your response>"}"""


def _build_system_prompt(language: str | None) -> str:
    if language and language in _SUPPORTED_LANGUAGES:
        lang = _LANGUAGE_INSTRUCTIONS[language]
    else:
        lang = "Always respond in the same language the user writes in."

    frontend_url = os.getenv("JUSSISPACE_FRONTEND_URL", "https://jussispace-production.lab.jussialanen.com").rstrip("/")

    return (
        "You are a helpful assistant for JussiSpace, a property rental service.\n"
        "You help users search for properties and check their order or booking status.\n"
        "When presenting properties, format each one as an HTML card with:\n"
        "  1. The primary image (use sizes.medium.webp if available, otherwise fall back to url).\n"
        "     Image URLs are already full URLs — use them directly as-is.\n"
        "     If a property has no images, omit the image tag.\n"
        f"  2. The property title as a bold HTML anchor linking to {frontend_url}/properties/<id>\n"
        "  3. City, type, price per month and status as a short line of text.\n"
        "Example card (image URL comes directly from the API response — never invent one):\n"
        f'<a href="{frontend_url}/properties/4"><img src="{{images[0].sizes.medium.webp}}" alt="Penthouse — Punavuori" /></a>\n'
        f'<strong><a href="{frontend_url}/properties/4">Penthouse — Punavuori</a></strong> · Helsinki · apartment · €3500/mo · available\n'
        "When presenting an order, include order ID (bold), property name, dates, status and total price.\n"
        "Example order: <strong>Order #42</strong> · Penthouse — Punavuori · 2024-06-01–2024-06-30 · <strong>approved</strong> · €3500\n"
        "Users may describe properties informally or colloquially. Always interpret such descriptions as property search requests.\n"
        "Examples: 'threesome' or 'kolmio' means a 3-bedroom/3-room apartment, 'kaksi' means 2 rooms, 'with a sauna' means sauna amenity required.\n"
        "Never refuse a property search request due to informal language — always translate it into a search.\n"
        "Never ask the user for more details before searching. Always call search_properties immediately with whatever information is available, then present the results.\n"
        f"{lang}\n\n"
        f"{_TOOLS_SPEC}"
    )


def _extract_json(text: str) -> dict | None:
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        return None
    try:
        return json.loads(match.group(0))
    except json.JSONDecodeError:
        return None


def _init_vertexai() -> None:
    project = os.getenv("GCP_PROJECT", "").strip()
    location = os.getenv("AGENT_GCP_LOCATION", "europe-north1").strip() or "europe-north1"
    if not project:
        raise RuntimeError("GCP_PROJECT environment variable is not set.")
    vertexai.init(project=project, location=location)


def ask(
    user_message: str,
    language: str | None = None,
    history: list[dict] | None = None,
) -> str:
    """
    Send a message to the JussiSpace agent and return its reply.

    Args:
        user_message: The user's input.
        language: Optional — 'fi' or 'en'. Mirrors user language when omitted.
        history: Optional list of previous messages for multi-turn chat.
                 Each item: {"role": "user"|"assistant", "content": "..."}
    """
    _init_vertexai()

    system_prompt = _build_system_prompt(language)
    model_name = os.getenv("JUSSISPACE_VERTEX_MODEL", os.getenv("AGENT_VERTEX_MODEL", "gemini-2.5-flash-lite")).strip() or "gemini-2.5-flash-lite"
    model = GenerativeModel(model_name, system_instruction=system_prompt)

    # Keep last 10 history messages to cap token usage
    messages = [
        {"role": m["role"], "content": m["content"]}
        for m in (history or [])[-10:]
    ]
    messages.append({"role": "user", "content": user_message})

    # Agentic loop — max 6 iterations to prevent runaway calls
    for _ in range(6):
        conversation = "\n\n".join(
            f"{'User' if m['role'] == 'user' else 'Assistant'}: {m['content']}"
            for m in messages
        )

        response = model.generate_content(conversation)
        response_text = response.text.strip()

        parsed = _extract_json(response_text)

        if not parsed or parsed.get("type") == "answer":
            return parsed["text"] if parsed and "text" in parsed else response_text

        if parsed.get("type") == "tool_call":
            tool_name = parsed.get("tool", "")
            params = parsed.get("params", {})

            if tool_name == "search_properties":
                all_props = _client.call_tool("search_properties", params)
                properties = all_props.get("data", [])
                if _rag.is_stale():
                    _rag.build(properties)
                matched = _rag.search(user_message, top_k=3)
                tool_result = {"data": matched, "total": len(matched)}
            else:
                tool_result = _client.call_tool(tool_name, params)

            tool_result_str = json.dumps(tool_result, ensure_ascii=False)[:50000]
            messages.append({"role": "assistant", "content": response_text})
            messages.append({
                "role": "user",
                "content": (
                    f"Tool '{tool_name}' returned: {tool_result_str}\n\n"
                    f"The user's original message was: \"{user_message}\"\n"
                    "Now provide the final answer to the user. You MUST respond in the exact same language the user wrote in."
                ),
            })
        else:
            return response_text

    return "Sorry, I was unable to complete the request."
