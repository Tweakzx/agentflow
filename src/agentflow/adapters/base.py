from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from agentflow.store import Task


@dataclass
class AdapterResult:
    success: bool
    note: str
    to_status: str = "review"


@dataclass
class AdapterContext:
    task: Task
    project: str
    repo_full_name: str | None
    previous_runs: list[dict[str, object]]
    gate_profile: dict[str, object] | None


class AgentAdapter(Protocol):
    name: str

    def execute(self, context: AdapterContext, agent_name: str) -> AdapterResult:
        """Run one task and return normalized lifecycle result."""
