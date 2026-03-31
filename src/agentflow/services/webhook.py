from __future__ import annotations

import threading
from dataclasses import dataclass
from typing import Callable

from agentflow.services.runner import Runner
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
        idem = f"gh:comment:{comment_id}" if comment_id else f"gh:issue:{issue_number}:run"
        trig = self.trigger_service.register_trigger(
            project=project,
            trigger_type="comment",
            trigger_ref=f"issue#{issue_number}:comment#{comment_id or 'unknown'}",
            idempotency_key=idem,
            payload=str(payload),
        )
        if bool(trig.get("duplicate", False)):
            return WebhookResult(accepted=True, duplicate=True, message="duplicate trigger ignored")

        task = self.store.get_task_by_external(project, "github", issue_number)
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

        if async_run:
            thread = threading.Thread(
                target=self._run_in_background,
                args=(project, task_id, adapter, agent_name, on_run_finished),
                daemon=True,
            )
            thread.start()
            return WebhookResult(accepted=True, duplicate=False, message="run queued", run_success=None)

        run = self.runner.run_task(project, task_id, adapter, agent_name)
        if run.task is None:
            return WebhookResult(accepted=True, duplicate=False, message=run.message, run_success=False)
        return WebhookResult(accepted=True, duplicate=False, message=run.message, run_success=run.success)

    def _run_in_background(
        self,
        project: str,
        task_id: int,
        adapter: str,
        agent_name: str,
        on_run_finished: Callable[[str, int, object], None] | None,
    ) -> None:
        run = self.runner.run_task(project, task_id, adapter, agent_name)
        if on_run_finished is not None:
            on_run_finished(project, task_id, run)
