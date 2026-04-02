from __future__ import annotations

import os
import time
from dataclasses import dataclass

from agentflow.adapters.base import AdapterContext
from agentflow.adapters.registry import AdapterRegistry
from agentflow.services.gates import GateEvaluator
from agentflow.services.ledger import build_event, build_gate_failed_event
from agentflow.store import Store, Task


@dataclass
class RunRecord:
    task: Task | None
    adapter: str
    success: bool
    message: str


@dataclass(frozen=True)
class PreparedRun:
    task: Task
    run_id: int
    adapter_name: str
    agent_name: str
    provenance: RunProvenance


@dataclass(frozen=True)
class RunProvenance:
    trigger_id: int | None
    trigger_type: str
    trigger_ref: str
    source_type: str
    source_ref: str

    @classmethod
    def manual(cls, adapter_name: str) -> "RunProvenance":
        runner_ref = f"runner:{adapter_name}"
        return cls(
            trigger_id=None,
            trigger_type="manual",
            trigger_ref=runner_ref,
            source_type="manual",
            source_ref=runner_ref,
        )


class Runner:
    def __init__(self, store: Store, registry: AdapterRegistry | None = None) -> None:
        self.store = store
        self.registry = registry or AdapterRegistry()

    def run_once(
        self,
        project: str,
        adapter_name: str,
        agent_name: str,
        lease_minutes: int = 30,
        *,
        provenance: RunProvenance | None = None,
    ) -> RunRecord:
        provenance = provenance or RunProvenance.manual(adapter_name)
        prepared_run = self.prepare_next_run(
            project,
            adapter_name,
            agent_name,
            lease_minutes=lease_minutes,
            provenance=provenance,
        )
        if prepared_run is None:
            return RunRecord(task=None, adapter=adapter_name, success=False, message="no claimable task")
        return self.execute_prepared_run(project, prepared_run)

    def run_task(
        self,
        project: str,
        task_id: int,
        adapter_name: str,
        agent_name: str,
        lease_minutes: int = 30,
        *,
        provenance: RunProvenance | None = None,
    ) -> RunRecord:
        provenance = provenance or RunProvenance.manual(adapter_name)
        prepared_run = self.prepare_task_run(
            project,
            task_id,
            adapter_name,
            agent_name,
            lease_minutes=lease_minutes,
            provenance=provenance,
        )
        if prepared_run is None:
            return RunRecord(task=None, adapter=adapter_name, success=False, message="task not claimable")
        return self.execute_prepared_run(project, prepared_run)

    def prepare_next_run(
        self,
        project: str,
        adapter_name: str,
        agent_name: str,
        lease_minutes: int = 30,
        *,
        provenance: RunProvenance | None = None,
    ) -> PreparedRun | None:
        provenance = provenance or RunProvenance.manual(adapter_name)
        task = self.store.claim_next_task(
            project,
            agent_name,
            lease_minutes=lease_minutes,
            ledger_event=self._build_task_claimed_ledger_event(adapter_name, agent_name, provenance),
        )
        if task is None:
            return None
        return self.prepare_claimed_task_run(project, task, adapter_name, agent_name, provenance=provenance)

    def prepare_task_run(
        self,
        project: str,
        task_id: int,
        adapter_name: str,
        agent_name: str,
        lease_minutes: int = 30,
        *,
        provenance: RunProvenance | None = None,
    ) -> PreparedRun | None:
        provenance = provenance or RunProvenance.manual(adapter_name)
        task = self.store.claim_task(
            task_id,
            project,
            agent_name,
            lease_minutes=lease_minutes,
            ledger_event=self._build_task_claimed_ledger_event(adapter_name, agent_name, provenance),
        )
        if task is None:
            return None
        return self.prepare_claimed_task_run(project, task, adapter_name, agent_name, provenance=provenance)

    def prepare_claimed_task_run(
        self,
        project: str,
        task: Task,
        adapter_name: str,
        agent_name: str,
        *,
        provenance: RunProvenance | None = None,
    ) -> PreparedRun:
        provenance = provenance or RunProvenance.manual(adapter_name)
        run_id = self.store.create_run(
            task_id=task.id,
            project=project,
            trigger_type=provenance.trigger_type,
            trigger_ref=provenance.trigger_ref,
            adapter=adapter_name,
            agent_name=agent_name,
            idempotency_key=f"{project}:{task.id}:{adapter_name}:{agent_name}:{time.time_ns()}",
        )
        self._append_run_started_event(project, task, run_id, adapter_name, agent_name, provenance)
        self.store.append_run_step(run_id, "claim", "passed", f"claimed by {agent_name}")
        return PreparedRun(
            task=task,
            run_id=run_id,
            adapter_name=adapter_name,
            agent_name=agent_name,
            provenance=provenance,
        )

    def execute_prepared_run(self, project: str, prepared_run: PreparedRun) -> RunRecord:
        return self._execute_prepared_run(project, prepared_run)

    def _execute_prepared_run(self, project: str, prepared_run: PreparedRun) -> RunRecord:
        task = prepared_run.task
        run_id = prepared_run.run_id
        adapter_name = prepared_run.adapter_name
        agent_name = prepared_run.agent_name
        provenance = prepared_run.provenance
        gate_profile = self.store.get_gate_profile(project)
        context = AdapterContext(
            task=task,
            project=project,
            repo_full_name=self.store.get_project_repo(project),
            previous_runs=[dict(r) for r in self.store.list_runs(task.id) if int(r["id"]) != run_id][:5],
            gate_profile=gate_profile,
        )
        adapter = self.registry.get(adapter_name)
        self._append_step_event(
            project,
            task=task,
            run_id=run_id,
            adapter_name=adapter_name,
            agent_name=agent_name,
            provenance=provenance,
            step_name="edit",
            event_type="step.started",
            summary=f"Adapter {adapter_name} started for task #{task.id}",
        )
        result = adapter.execute(context, agent_name)
        self._append_step_event(
            project,
            task=task,
            run_id=run_id,
            adapter_name=adapter_name,
            agent_name=agent_name,
            provenance=provenance,
            step_name="edit",
            event_type="step.passed" if result.success else "step.failed",
            summary=result.note,
            severity="info" if result.success else "error",
            evidence={"step_name": "edit", "log_excerpt": result.note},
        )
        self.store.append_run_step(run_id, "edit", "passed" if result.success else "failed", result.note)

        gate_passed = True
        gate_ran = False
        gate_summary = "gate skipped"
        if gate_profile is not None:
            commands = gate_profile.get("commands", [])
            timeout_sec = int(gate_profile.get("timeout_sec", 1800))
            if isinstance(commands, list) and commands:
                gate_ran = True
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
        if gate_ran:
            self._append_gate_event(
                project,
                task=task,
                run_id=run_id,
                adapter_name=adapter_name,
                agent_name=agent_name,
                provenance=provenance,
                gate_passed=gate_passed,
                gate_summary=gate_summary,
                gate_profile=gate_profile,
            )
            self.store.append_run_step(
                run_id,
                "gate",
                "passed" if gate_passed else "failed",
                gate_summary,
                None if gate_passed else "gate_failed",
            )

        if result.success and gate_passed:
            self.store.move_task(
                task.id,
                result.to_status,
                result.note,
                ledger_event=self._build_task_status_changed_ledger_event(
                    run_id,
                    adapter_name,
                    agent_name,
                    provenance,
                    result.note,
                    result.to_status,
                ),
            )
            self.store.finalize_run(run_id, "passed", gate_passed=True, result_summary=result.note)
            self._append_run_finished_event(
                project,
                task_id=task.id,
                run_id=run_id,
                adapter_name=adapter_name,
                agent_name=agent_name,
                provenance=provenance,
                summary=result.note,
            )
        else:
            if not gate_passed:
                message = f"gate failed: {gate_summary}"
                error_code = "gate_failed"
            else:
                message = result.note
                error_code = "execution_failed"
            self.store.move_task(
                task.id,
                "blocked",
                message,
                ledger_event=self._build_task_status_changed_ledger_event(
                    run_id,
                    adapter_name,
                    agent_name,
                    provenance,
                    message,
                    "blocked",
                ),
            )
            self.store.finalize_run(
                run_id,
                "failed",
                gate_passed=gate_passed,
                result_summary=message,
                error_code=error_code,
            )
            self._append_run_finished_event(
                project,
                task_id=task.id,
                run_id=run_id,
                adapter_name=adapter_name,
                agent_name=agent_name,
                provenance=provenance,
                summary=message,
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

    def _build_task_claimed_ledger_event(
        self,
        adapter_name: str,
        agent_name: str,
        provenance: RunProvenance,
    ) -> dict[str, object]:
        return build_event(
            event_family="dispatch",
            event_type="task.claimed",
            actor_type="agent",
            actor_id=agent_name,
            trigger_id=provenance.trigger_id,
            summary=f"Task claimed by {agent_name}",
            source_type=provenance.source_type,
            source_ref=provenance.source_ref,
            context={"adapter": adapter_name},
        )

    def _append_run_started_event(
        self,
        project: str,
        task: Task,
        run_id: int,
        adapter_name: str,
        agent_name: str,
        provenance: RunProvenance,
    ) -> int:
        event = build_event(
            event_family="execution",
            event_type="run.started",
            actor_type="agent",
            actor_id=agent_name,
            task_id=task.id,
            run_id=run_id,
            trigger_id=provenance.trigger_id,
            summary=f"Run started for task #{task.id}",
            source_type=provenance.source_type,
            source_ref=provenance.source_ref,
            status_from=task.status,
            status_to=task.status,
            run_status_to="running",
            evidence={"adapter": adapter_name},
            context={"adapter": adapter_name},
        )
        return self._append_ledger_event(project, event)

    def _append_step_event(
        self,
        project: str,
        *,
        task: Task,
        run_id: int,
        adapter_name: str,
        agent_name: str,
        provenance: RunProvenance,
        step_name: str,
        event_type: str,
        summary: str,
        severity: str = "info",
        evidence: dict[str, object] | None = None,
    ) -> int:
        event_evidence = {"step_name": step_name}
        if evidence:
            event_evidence.update(evidence)
        event = build_event(
            event_family="execution",
            event_type=event_type,
            actor_type="agent",
            actor_id=agent_name,
            task_id=task.id,
            run_id=run_id,
            trigger_id=provenance.trigger_id,
            summary=summary,
            severity=severity,
            source_type=provenance.source_type,
            source_ref=provenance.source_ref,
            status_from=task.status,
            status_to=task.status,
            run_status_from="running",
            run_status_to="running",
            evidence=event_evidence,
            context={"adapter": adapter_name},
        )
        return self._append_ledger_event(project, event)

    def _append_gate_event(
        self,
        project: str,
        *,
        task: Task,
        run_id: int,
        adapter_name: str,
        agent_name: str,
        provenance: RunProvenance,
        gate_passed: bool,
        gate_summary: str,
        gate_profile: dict[str, object] | None,
    ) -> int:
        if gate_passed:
            event = build_event(
                event_family="risk",
                event_type="gate.passed",
                actor_type="system",
                actor_id=agent_name,
                task_id=task.id,
                run_id=run_id,
                trigger_id=provenance.trigger_id,
                summary=gate_summary,
                source_type=provenance.source_type,
                source_ref=provenance.source_ref,
                status_from=task.status,
                status_to=task.status,
                run_status_from="running",
                run_status_to="running",
                evidence={
                    "step_name": "gate",
                    "required_checks": [] if gate_profile is None else gate_profile.get("required_checks", []),
                },
                context={"adapter": adapter_name},
            )
        else:
            event = build_gate_failed_event(
                task_id=task.id,
                run_id=run_id,
                actor_id=agent_name,
                summary=f"Gate failed on task #{task.id}: {gate_summary}",
                error_code="gate_failed",
                log_excerpt=gate_summary,
                context={"adapter": adapter_name},
            )
            event["trigger_id"] = provenance.trigger_id
            event["source_type"] = provenance.source_type
            event["source_ref"] = provenance.source_ref
            event["status_from"] = task.status
            event["status_to"] = task.status
            event["run_status_from"] = "running"
            event["run_status_to"] = "running"
        return self._append_ledger_event(project, event)

    def _build_task_status_changed_ledger_event(
        self,
        run_id: int,
        adapter_name: str,
        agent_name: str,
        provenance: RunProvenance,
        summary: str,
        to_status: str,
    ) -> dict[str, object]:
        return build_event(
            event_family="governance",
            event_type="task.status_changed",
            actor_type="agent",
            actor_id=agent_name,
            run_id=run_id,
            trigger_id=provenance.trigger_id,
            summary=summary,
            severity="error" if to_status == "blocked" else "info",
            source_type=provenance.source_type,
            source_ref=provenance.source_ref,
            run_status_from="running",
            run_status_to="passed" if to_status != "blocked" else "failed",
            evidence={"note": summary},
            context={"adapter": adapter_name},
        )

    def _append_run_finished_event(
        self,
        project: str,
        task_id: int,
        run_id: int,
        adapter_name: str,
        agent_name: str,
        provenance: RunProvenance,
        summary: str,
    ) -> int:
        run_row = self.store.list_runs(task_id)[0]
        task = self.store.get_task(task_id)
        event = build_event(
            event_family="execution",
            event_type="run.finished",
            actor_type="agent",
            actor_id=agent_name,
            task_id=task_id,
            run_id=run_id,
            trigger_id=provenance.trigger_id,
            summary=summary,
            severity="error" if str(run_row["status"]) == "failed" else "info",
            source_type=provenance.source_type,
            source_ref=provenance.source_ref,
            status_to=task.status if task is not None else None,
            run_status_from="running",
            run_status_to=str(run_row["status"]),
            evidence={
                "gate_passed": bool(run_row["gate_passed"]),
                "error_code": run_row["error_code"],
            },
            context={"adapter": adapter_name},
        )
        return self._append_ledger_event(project, event)

    def _append_ledger_event(self, project: str, event: dict[str, object]) -> int:
        return self.store.append_ledger_event(
            project=project,
            task_id=int(event["task_id"]) if "task_id" in event else None,
            run_id=int(event["run_id"]) if "run_id" in event else None,
            trigger_id=int(event["trigger_id"]) if event.get("trigger_id") is not None else None,
            parent_event_id=int(event["parent_event_id"]) if "parent_event_id" in event else None,
            event_family=str(event["event_family"]),
            event_type=str(event["event_type"]),
            actor_type=str(event["actor_type"]),
            actor_id=str(event["actor_id"]) if event.get("actor_id") is not None else None,
            source_type=str(event["source_type"]) if event.get("source_type") is not None else None,
            source_ref=str(event["source_ref"]) if event.get("source_ref") is not None else None,
            status_from=str(event["status_from"]) if event.get("status_from") is not None else None,
            status_to=str(event["status_to"]) if event.get("status_to") is not None else None,
            run_status_from=str(event["run_status_from"]) if event.get("run_status_from") is not None else None,
            run_status_to=str(event["run_status_to"]) if event.get("run_status_to") is not None else None,
            severity=str(event["severity"]),
            summary=str(event["summary"]),
            evidence=event.get("evidence") if isinstance(event.get("evidence"), dict) else None,
            next_action=event.get("next_action") if isinstance(event.get("next_action"), dict) else None,
            context=event.get("context") if isinstance(event.get("context"), dict) else None,
            idempotency_key=str(event["idempotency_key"]) if event.get("idempotency_key") is not None else None,
            occurred_at=str(event["occurred_at"]) if event.get("occurred_at") is not None else None,
        )
