"""
One agent loop for every agent: the model calls tools natively until it answers.
"""
import json
import logging
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import httpx

from aibot.agents.config import AgentConfig, ToolConfig
from aibot.knowledge.rag import Ranker
from aibot.knowledge.render import render_data
from aibot.knowledge.sources import ContextSource
from aibot.llm import LLMProvider, Message, ProviderNotConfigured, ProviderRegistry, ToolSpec
from aibot.tools.http import AuthSession, HttpTool

logger = logging.getLogger(__name__)

FALLBACK_REPLY = "Sorry, I was unable to complete the request."


class AgentUnavailable(RuntimeError):
    """The agent cannot run with the current configuration (maps to HTTP 503)."""


@dataclass
class ChatTurn:
    """A previous message supplied by the caller."""

    role: str
    content: str


class Agent:
    """A configured agent, ready to chat."""

    def __init__(
        self,
        config: AgentConfig,
        providers: ProviderRegistry,
        http: Callable[[], httpx.AsyncClient],
        ranker: Ranker,
    ) -> None:
        self.config = config
        self._providers = providers
        self._http = http
        self._ranker = ranker
        sessions = {name: AuthSession(auth) for name, auth in config.auth.items()}
        self._tools = {
            tool.name: HttpTool(tool, sessions.get(tool.http.auth) if tool.http.auth else None)
            for tool in config.tools
        }
        self._contexts = [ContextSource(source) for source in config.context]
        self._tool_specs = [
            ToolSpec(name=tool.name, description=tool.description, parameters=tool.parameters)
            for tool in config.tools
        ]

    def _provider(self) -> LLMProvider:
        provider = self._providers.get(self.config.provider)
        if self._tool_specs and not provider.supports_tools:
            raise AgentUnavailable(
                f"Provider '{provider.name}' does not support tool calling, "
                f"which agent '{self.config.id}' needs."
            )
        return provider

    def _embedding_provider(self, chat_provider: LLMProvider) -> LLMProvider:
        name = self.config.embedding.provider
        if name:
            return self._providers.get(name)
        if chat_provider.supports_embeddings:
            return chat_provider
        return self._providers.get("gemini")

    async def system_prompt(self, language: str | None) -> str:
        """The system prompt with the language instruction and context data."""
        parts = [self.config.system_prompt.strip(), self.config.language_instruction(language)]
        for source in self._contexts:
            parts.append(f"{source.config.title}:\n{await source.text(self._http())}")
        return "\n\n".join(parts)

    async def chat(self, message: str, language: str | None = None, history: list[ChatTurn] | None = None) -> str:
        """Answer one user message, calling tools as needed."""
        provider = self._provider()
        system = await self.system_prompt(language)
        limit = self.config.history_limit
        recent = (history or [])[-limit:] if limit else []
        messages = [
            Message(role="assistant" if turn.role == "assistant" else "user", content=turn.content)
            for turn in recent
        ]
        messages.append(Message(role="user", content=message))

        for _ in range(self.config.max_steps):
            response = await provider.generate(
                messages,
                model=self.config.model or None,
                system=system,
                tools=self._tool_specs or None,
                temperature=self.config.temperature,
            )
            if not response.tool_calls:
                return response.text or FALLBACK_REPLY

            messages.append(Message(
                role="assistant",
                content=response.text,
                tool_calls=response.tool_calls,
                raw=response.raw_message,
            ))
            for call in response.tool_calls:
                result = await self._run_tool(call.name, call.arguments, message, provider)
                messages.append(Message(
                    role="tool",
                    content=self._serialize(call.name, result),
                    tool_call_id=call.id,
                    name=call.name,
                ))

        logger.warning("Agent %s reached max_steps without an answer", self.config.id)
        return FALLBACK_REPLY

    async def _run_tool(self, name: str, arguments: dict[str, Any], query: str, provider: LLMProvider) -> Any:
        tool = self._tools.get(name)
        if tool is None:
            return {"error": f"unknown tool '{name}'"}
        result = await tool.call(arguments, self._http())
        if tool.config.rag:
            result = await self._rank(tool.config, result, query, provider)
        return result

    async def _rank(self, tool: ToolConfig, result: Any, query: str, provider: LLMProvider) -> Any:
        rag = tool.rag
        if not isinstance(result, dict) or not isinstance(result.get(rag.data_field), list):
            return result
        items = result[rag.data_field]
        texts = [
            render_data(item, fields=rag.fields, max_text_length=rag.max_text_length)
            if isinstance(item, dict) else str(item)
            for item in items
        ]
        try:
            embedder = self._embedding_provider(provider)
        except ProviderNotConfigured:
            return {**result, rag.data_field: items[:rag.top_k], "total": min(len(items), rag.top_k)}
        matched = await self._ranker.rank(
            embedder, self.config.embedding.model or None, query, items, texts, rag.top_k,
        )
        return {**result, rag.data_field: matched, "total": len(matched)}

    def _serialize(self, name: str, result: Any) -> str:
        limit = next((t.max_result_chars for t in self.config.tools if t.name == name), 50000)
        return json.dumps(result, ensure_ascii=False, default=str)[:limit]
