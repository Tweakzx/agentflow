from __future__ import annotations

from agentflow.adapters.base import AgentAdapter
from agentflow.adapters.mock import MockAdapter
from agentflow.adapters.openclaw import OpenClawAdapter


class AdapterRegistry:
    def __init__(self) -> None:
        self._adapters: dict[str, AgentAdapter] = {}
        self.register(MockAdapter())
        self.register(OpenClawAdapter())

    def register(self, adapter: AgentAdapter) -> None:
        self._adapters[adapter.name] = adapter

    def get(self, name: str) -> AgentAdapter:
        if name not in self._adapters:
            supported = ", ".join(sorted(self._adapters.keys()))
            raise ValueError(f"Adapter '{name}' not found. Supported: {supported}")
        return self._adapters[name]

    def names(self) -> list[str]:
        return sorted(self._adapters.keys())
