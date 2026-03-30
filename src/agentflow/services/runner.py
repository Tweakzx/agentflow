from __future__ import annotations

from dataclasses import dataclass

from agentflow.adapters.registry import AdapterRegistry
from agentflow.store import Store, Task


@dataclass
class RunRecord:
    task: Task | None
    adapter: str
    success: bool
    message: str


class Runner:
    def __init__(self, store: Store, registry: AdapterRegistry | None = None) -> None:
        self.store = store
        self.registry = registry or AdapterRegistry()

    def run_once(self, project: str, adapter_name: str, agent_name: str, lease_minutes: int = 30) -> RunRecord:
        task = self.store.claim_next_task(project, agent_name, lease_minutes=lease_minutes)
        if task is None:
            return RunRecord(task=None, adapter=adapter_name, success=False, message="no claimable task")

        adapter = self.registry.get(adapter_name)
        result = adapter.execute(task, agent_name)
        self.store.move_task(task.id, result.to_status, result.note)
        latest = [t for t in self.store.list_tasks(project) if t.id == task.id][0]
        return RunRecord(task=latest, adapter=adapter_name, success=result.success, message=result.note)

    def run_batch(
        self,
        project: str,
        adapter_name: str,
        agent_prefix: str,
        count: int,
        lease_minutes: int = 30,
    ) -> list[RunRecord]:
        out: list[RunRecord] = []
        for i in range(count):
            agent_name = f"{agent_prefix}-{i + 1}"
            out.append(self.run_once(project, adapter_name, agent_name, lease_minutes=lease_minutes))
        return out
