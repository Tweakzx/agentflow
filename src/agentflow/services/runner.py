from __future__ import annotations

import os
import time
from dataclasses import dataclass

from agentflow.adapters.base import AdapterContext
from agentflow.adapters.registry import AdapterRegistry
from agentflow.services.gates import GateEvaluator
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

        return self._run_claimed_task(project, task, adapter_name, agent_name)

    def run_task(
        self,
        project: str,
        task_id: int,
        adapter_name: str,
        agent_name: str,
        lease_minutes: int = 30,
    ) -> RunRecord:
        task = self.store.claim_task(task_id, project, agent_name, lease_minutes=lease_minutes)
        if task is None:
            return RunRecord(task=None, adapter=adapter_name, success=False, message="task not claimable")

        return self._run_claimed_task(project, task, adapter_name, agent_name)

    def _run_claimed_task(self, project: str, task: Task, adapter_name: str, agent_name: str) -> RunRecord:
        run_id = self.store.create_run(
            task_id=task.id,
            project=project,
            trigger_type="manual",
            trigger_ref=f"runner:{adapter_name}",
            adapter=adapter_name,
            agent_name=agent_name,
            idempotency_key=f"{project}:{task.id}:{adapter_name}:{agent_name}:{time.time_ns()}",
        )
        self.store.append_run_step(run_id, "claim", "passed", f"claimed by {agent_name}")

        gate_profile = self.store.get_gate_profile(project)
        context = AdapterContext(
            task=task,
            project=project,
            repo_full_name=self.store.get_project_repo(project),
            previous_runs=[dict(r) for r in self.store.list_runs(task.id) if int(r["id"]) != run_id][:5],
            gate_profile=gate_profile,
        )
        adapter = self.registry.get(adapter_name)
        result = adapter.execute(context, agent_name)
        self.store.append_run_step(run_id, "edit", "passed" if result.success else "failed", result.note)

        gate_passed = True
        gate_summary = "gate skipped"
        if gate_profile is not None:
            commands = gate_profile.get("commands", [])
            timeout_sec = int(gate_profile.get("timeout_sec", 1800))
            if isinstance(commands, list) and commands:
                evaluator = GateEvaluator(
                    timeout_sec=timeout_sec,
                    cwd=self._resolve_workspace(context.repo_full_name),
                    allowed_prefixes=self._allowed_gate_prefixes(),
                )
                gate_result = evaluator.evaluate([str(c) for c in commands])
                gate_passed = gate_result.passed
                gate_summary = "; ".join(
                    [f"{c.command} => {'ok' if c.passed else 'fail'}" for c in gate_result.checks]
                )
                self.store.append_run_step(
                    run_id,
                    "gate",
                    "passed" if gate_result.passed else "failed",
                    gate_summary,
                )

        if result.success and gate_passed:
            self.store.move_task(task.id, result.to_status, result.note)
            self.store.finalize_run(run_id, "passed", gate_passed=True, result_summary=result.note)
        else:
            if not gate_passed:
                message = f"gate failed: {gate_summary}"
                error_code = "gate_failed"
            else:
                message = result.note
                error_code = "execution_failed"
            self.store.move_task(task.id, "blocked", message)
            self.store.finalize_run(
                run_id,
                "failed",
                gate_passed=gate_passed,
                result_summary=message,
                error_code=error_code,
            )

        latest = [t for t in self.store.list_tasks(project) if t.id == task.id][0]
        if latest.status == "blocked" and not gate_passed:
            return RunRecord(task=latest, adapter=adapter_name, success=False, message=f"gate failed: {gate_summary}")
        return RunRecord(task=latest, adapter=adapter_name, success=result.success and gate_passed, message=result.note)

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

    def _resolve_workspace(self, repo_full_name: str | None) -> str | None:
        if not repo_full_name:
            return None
        root = os.environ.get("AGENTFLOW_WORKSPACE_ROOT", os.path.expanduser("~/github"))
        workspace = os.path.join(root, repo_full_name)
        return workspace if os.path.isdir(workspace) else None

    def _allowed_gate_prefixes(self) -> list[str] | None:
        raw = os.environ.get("AGENTFLOW_GATE_ALLOWED_PREFIXES", "").strip()
        if not raw:
            return None
        vals = [x.strip() for x in raw.split(",") if x.strip()]
        return vals or None
