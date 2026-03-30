from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from agentflow.store import Task


@dataclass
class AdapterResult:
    success: bool
    note: str
    to_status: str = "pr_ready"


class AgentAdapter(Protocol):
    name: str

    def execute(self, task: Task, agent_name: str) -> AdapterResult:
        """Run one task and return normalized lifecycle result."""
