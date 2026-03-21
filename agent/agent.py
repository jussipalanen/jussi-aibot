import os
import vertexai
from vertexai.generative_models import GenerativeModel, Content, Part
from agent.tools import jussispace_tools
from agent.client import JussispaceClient

vertexai.init(project=os.environ["GCP_PROJECT"], location=os.environ["GCP_LOCATION"])

client = JussispaceClient()

_SUPPORTED_LANGUAGES = {"fi", "en"}

_LANGUAGE_INSTRUCTIONS = {
    "fi": "Vastaa aina suomeksi.",
    "en": "Always respond in English.",
}

_BASE_SYSTEM_PROMPT = """You are a helpful assistant for JussiSpace, a property rental service.
You help users search for properties and check their order/booking status.
When presenting properties, include title, city, type, price and status.
When presenting an order, include order ID, property name, dates, status and total price."""


def _build_system_prompt(language: str | None) -> str:
    if language and language in _SUPPORTED_LANGUAGES:
        return f"{_BASE_SYSTEM_PROMPT}\n{_LANGUAGE_INSTRUCTIONS[language]}"
    # No language specified — let Gemini mirror the user's language
    return f"{_BASE_SYSTEM_PROMPT}\nAlways respond in the same language the user writes in."


def ask(user_message: str, language: str | None = None) -> str:
    """
    Send a message to the JussiSpace agent and return its reply.

    Args:
        user_message: The user's input.
        language: Optional language code — 'fi' (Finnish) or 'en' (English).
                  When omitted the agent mirrors the language of the user's message.
    """
    system_prompt = _build_system_prompt(language)
    model = GenerativeModel("gemini-1.5-pro", system_instruction=system_prompt, tools=[jussispace_tools])
    chat = model.start_chat()

    response = chat.send_message(user_message)

    # Agentic loop — Gemini may call multiple tools
    while response.candidates[0].finish_reason.name == "TOOL_CALLS":
        tool_call = response.candidates[0].content.parts[0].function_call
        tool_result = client.call_tool(tool_call.name, dict(tool_call.args))

        response = chat.send_message(
            Content(parts=[Part.from_function_response(name=tool_call.name, response={"result": tool_result})])
        )

    return response.text
