from __future__ import annotations

from agentflow.adapters.base import AdapterContext, AdapterResult


class MockAdapter:
    """A deterministic local adapter for smoke tests and demo runs."""

    name = "mock"

    def execute(self, context: AdapterContext, agent_name: str) -> AdapterResult:
        task = context.task
        title = task.title.lower()
        if "blocked" in title or "investigate" in title:
            return AdapterResult(success=False, note=f"{agent_name} requires human input", to_status="blocked")
        if "design" in title or "proposal" in title:
            return AdapterResult(success=True, note=f"{agent_name} prepared design notes", to_status="approved")
        return AdapterResult(success=True, note=f"{agent_name} produced implementation plan", to_status="pr_ready")
