"""
Loads agent definitions from YAML and builds agents on first use.
"""
from collections.abc import Callable
from pathlib import Path

import httpx
from pydantic import ValidationError

from aibot.agents.config import AgentConfig
from aibot.agents.engine import Agent
from aibot.configfile import load_yaml_dir
from aibot.knowledge.rag import Ranker
from aibot.llm import ProviderRegistry


class ConfigError(ValueError):
    """A config file is invalid."""


class AgentRegistry:
    """All configured agents, by id."""

    def __init__(
        self,
        configs: list[AgentConfig],
        providers: ProviderRegistry,
        http: Callable[[], httpx.AsyncClient],
        ranker: Ranker | None = None,
    ) -> None:
        self.configs: dict[str, AgentConfig] = {}
        for config in configs:
            if config.id in self.configs:
                raise ConfigError(f"Duplicate agent id '{config.id}'.")
            self.configs[config.id] = config
        self._providers = providers
        self._http = http
        self._ranker = ranker or Ranker()
        self._agents: dict[str, Agent] = {}

    @staticmethod
    def load_configs(directory: Path) -> list[AgentConfig]:
        """Parse and validate every agent file in a directory."""
        configs = []
        for path, data in load_yaml_dir(directory):
            try:
                configs.append(AgentConfig.model_validate(data))
            except ValidationError as exc:
                raise ConfigError(f"Invalid agent config {path.name}:\n{exc}") from exc
        return configs

    def ids(self) -> list[str]:
        return sorted(self.configs)

    def has(self, agent_id: str) -> bool:
        return agent_id in self.configs

    def get(self, agent_id: str) -> Agent:
        """Return the agent, building it on first use."""
        if agent_id not in self._agents:
            self._agents[agent_id] = Agent(self.configs[agent_id], self._providers, self._http, self._ranker)
        return self._agents[agent_id]
