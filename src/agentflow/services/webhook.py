from __future__ import annotations

from dataclasses import dataclass

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
    ) -> WebhookResult:
        comment = payload.get("comment", {})
        body = str(getattr(comment, "get", lambda _k, _d=None: "")("body", "") if isinstance(comment, dict) else "")
        if "/agentflow run" not in body:
            return WebhookResult(accepted=False, duplicate=False, message="ignored: no command")

        issue = payload.get("issue", {})
        issue_number = str(getattr(issue, "get", lambda _k, _d=None: "")("number", "") if isinstance(issue, dict) else "")
        if not issue_number:
            return WebhookResult(accepted=False, duplicate=False, message="ignored: missing issue number")

        comment_id = str(getattr(comment, "get", lambda _k, _d=None: "")("id", "") if isinstance(comment, dict) else "")
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
            title = str(getattr(issue, "get", lambda _k, _d=None: "")("title", "")) or f"issue-{issue_number}"
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

        run = self.runner.run_task(project, task_id, adapter, agent_name)
        if run.task is None:
            return WebhookResult(accepted=True, duplicate=False, message=run.message, run_success=False)
        return WebhookResult(accepted=True, duplicate=False, message=run.message, run_success=run.success)
