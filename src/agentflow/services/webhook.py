from __future__ import annotations

import threading
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Callable

from agentflow.services.runner import PreparedRun
from agentflow.services.runner import Runner
from agentflow.services.runner import RunProvenance
from agentflow.services.triggers import TriggerService
from agentflow.store import Store


@dataclass
class WebhookResult:
    accepted: bool
    duplicate: bool
    message: str
    run_success: bool | None = None


class GithubCommentWebhookService:
    def __init__(self, store: Store, runner: Runner, trigger_service: TriggerService | None = None) -> None:
        self.store = store
        self.runner = runner
        self.trigger_service = trigger_service or TriggerService(store)
        self._idempotency_locks: dict[str, threading.Lock] = {}
        self._idempotency_lock_refs: dict[str, int] = {}
        self._idempotency_locks_guard = threading.Lock()

    def handle_pr_comment(
        self,
        *,
        project: str,
        payload: dict[str, object],
        adapter: str,
        agent_name: str,
        async_run: bool = False,
        on_run_finished: Callable[[str, int, object], None] | None = None,
    ) -> WebhookResult:
        comment = payload.get("comment")
        if not isinstance(comment, dict):
            return WebhookResult(accepted=False, duplicate=False, message="ignored: malformed payload: comment is not a dict")
        body = str(comment.get("body", ""))
        if "/agentflow run" not in body:
            return WebhookResult(accepted=False, duplicate=False, message="ignored: no command")

        issue = payload.get("issue")
        if not isinstance(issue, dict):
            return WebhookResult(accepted=False, duplicate=False, message="ignored: malformed payload: issue is not a dict")
        issue_number = str(issue.get("number", ""))
        if not issue_number:
            return WebhookResult(accepted=False, duplicate=False, message="ignored: missing issue number")

        comment_id = str(comment.get("id", ""))
        source_ref = f"issue#{issue_number}:comment#{comment_id or 'unknown'}"
        actor_id = self._comment_actor_id(comment)
        idem = f"gh:comment:{comment_id}" if comment_id else f"gh:issue:{issue_number}:run"
        with self._idempotency_key_lock(idem):
            task = self.store.get_task_by_external(project, "github", issue_number)
            trig = self.trigger_service.register_trigger(
                project=project,
                trigger_type="comment",
                trigger_ref=source_ref,
                idempotency_key=idem,
                payload=str(payload),
            )
            trigger_id = int(trig["trigger_id"]) if trig.get("trigger_id") is not None else None
            if bool(trig.get("duplicate", False)):
                self.store.append_ledger_event(
                    project=project,
                    task_id=task.id if task is not None else None,
                    run_id=None,
                    trigger_id=trigger_id,
                    parent_event_id=None,
                    event_family="feedback",
                    event_type="comment.received",
                    actor_type="user",
                    actor_id=actor_id,
                    source_type="github",
                    source_ref=source_ref,
                    status_from=None,
                    status_to=None,
                    run_status_from=None,
                    run_status_to=None,
                    severity="warning",
                    summary=f"Duplicate GitHub comment ignored for issue #{issue_number}",
                    evidence={
                        "comment_id": comment_id,
                        "issue_number": issue_number,
                        "duplicate": True,
                        "disposition": "ignored",
                        "command": "run",
                    },
                    next_action=None,
                    context={"adapter": adapter, "agent_name": agent_name},
                    idempotency_key=f"{idem}:feedback:duplicate",
                )
                return WebhookResult(accepted=True, duplicate=True, message="duplicate trigger ignored")

            if task is None:
                title = str(issue.get("title", "")) or f"issue-{issue_number}"
                task_id = self.store.add_task(
                    project=project,
                    title=title,
                    description=None,
                    priority=3,
                    impact=3,
                    effort=3,
                    source="github",
                    external_id=issue_number,
                )
            else:
                task_id = task.id

            provenance = RunProvenance(
                trigger_id=trigger_id,
                trigger_type="comment",
                trigger_ref=source_ref,
                source_type="github",
                source_ref=source_ref,
            )

            prepared_run = self.runner.prepare_task_run(
                project,
                task_id,
                adapter,
                agent_name,
                provenance=provenance,
            )
            if prepared_run is None:
                self.store.delete_trigger_by_key(idem)
                self._append_comment_received_event(
                    project=project,
                    task_id=task_id,
                    trigger_id=None,
                    actor_id=actor_id,
                    source_ref=source_ref,
                    issue_number=issue_number,
                    comment_id=comment_id,
                    adapter=adapter,
                    agent_name=agent_name,
                    disposition="rejected",
                    summary=f"GitHub comment could not start a run for issue #{issue_number}",
                    severity="warning",
                    run_status_to=None,
                    idempotency_key=f"{idem}:feedback:rejected:{task_id}",
                )
                return WebhookResult(accepted=True, duplicate=False, message="task not claimable", run_success=False)

            self._append_comment_received_event(
                project=project,
                task_id=task_id,
                trigger_id=trigger_id,
                actor_id=actor_id,
                source_ref=source_ref,
                issue_number=issue_number,
                comment_id=comment_id,
                adapter=adapter,
                agent_name=agent_name,
                disposition="queued" if async_run else "accepted",
                summary=(
                    f"GitHub comment queued a run for issue #{issue_number}"
                    if async_run
                    else f"GitHub comment received for issue #{issue_number}"
                ),
                severity="info",
                run_status_to="queued" if async_run else None,
                idempotency_key=f"{idem}:feedback:accepted",
            )

            if async_run:
                thread = threading.Thread(
                    target=self._run_in_background,
                    args=(project, prepared_run, on_run_finished),
                    daemon=True,
                )
                thread.start()
                return WebhookResult(accepted=True, duplicate=False, message="run queued", run_success=None)

            run = self.runner.execute_prepared_run(project, prepared_run)
            return WebhookResult(accepted=True, duplicate=False, message=run.message, run_success=run.success)

    def _run_in_background(
        self,
        project: str,
        prepared_run: PreparedRun,
        on_run_finished: Callable[[str, int, object], None] | None,
    ) -> None:
        run = self.runner.execute_prepared_run(project, prepared_run)
        if on_run_finished is not None:
            on_run_finished(project, prepared_run.task.id, run)

    def _append_comment_received_event(
        self,
        *,
        project: str,
        task_id: int,
        trigger_id: int | None,
        actor_id: str | None,
        source_ref: str,
        issue_number: str,
        comment_id: str,
        adapter: str,
        agent_name: str,
        disposition: str,
        summary: str,
        severity: str,
        run_status_to: str | None,
        idempotency_key: str,
    ) -> None:
        self.store.append_ledger_event(
            project=project,
            task_id=task_id,
            run_id=None,
            trigger_id=trigger_id,
            parent_event_id=None,
            event_family="feedback",
            event_type="comment.received",
            actor_type="user",
            actor_id=actor_id,
            source_type="github",
            source_ref=source_ref,
            status_from=None,
            status_to=None,
            run_status_from=None,
            run_status_to=run_status_to,
            severity=severity,
            summary=summary,
            evidence={
                "comment_id": comment_id,
                "issue_number": issue_number,
                "duplicate": False,
                "disposition": disposition,
                "command": "run",
            },
            next_action=None,
            context={"adapter": adapter, "agent_name": agent_name},
            idempotency_key=idempotency_key,
        )

    def _comment_actor_id(self, comment: dict[str, object]) -> str | None:
        user = comment.get("user")
        if isinstance(user, dict):
            for key in ("login", "name", "email"):
                value = user.get(key)
                if value is not None:
                    text = str(value).strip()
                    if text:
                        return text
        return None

    @contextmanager
    def _idempotency_key_lock(self, idempotency_key: str):
        with self._idempotency_locks_guard:
            lock = self._idempotency_locks.get(idempotency_key)
            if lock is None:
                lock = threading.Lock()
                self._idempotency_locks[idempotency_key] = lock
                self._idempotency_lock_refs[idempotency_key] = 0
            self._idempotency_lock_refs[idempotency_key] += 1

        lock.acquire()
        try:
            yield
        finally:
            lock.release()
            with self._idempotency_locks_guard:
                remaining = self._idempotency_lock_refs[idempotency_key] - 1
                if remaining <= 0:
                    self._idempotency_lock_refs.pop(idempotency_key, None)
                    self._idempotency_locks.pop(idempotency_key, None)
                else:
                    self._idempotency_lock_refs[idempotency_key] = remaining
