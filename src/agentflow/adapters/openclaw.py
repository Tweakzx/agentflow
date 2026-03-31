from __future__ import annotations

import json
import os
import urllib.error
import urllib.request

from agentflow.adapters.base import AdapterContext, AdapterResult


class OpenClawAdapter:
    """Dispatch one task to an OpenClaw gateway session endpoint."""

    name = "openclaw"

    def __init__(
        self,
        gateway_url: str | None = None,
        *,
        runtime: str | None = None,
        timeout_sec: int | None = None,
    ) -> None:
        self.gateway_url = (gateway_url or os.environ.get("AGENTFLOW_OPENCLAW_GATEWAY") or "http://127.0.0.1:3000").rstrip(
            "/"
        )
        self.runtime = runtime or os.environ.get("AGENTFLOW_OPENCLAW_RUNTIME") or "acp"
        self.timeout_sec = timeout_sec or int(os.environ.get("AGENTFLOW_OPENCLAW_TIMEOUT_SEC", "1800"))
        self.api_token = os.environ.get("AGENTFLOW_OPENCLAW_TOKEN")

    def execute(self, context: AdapterContext, agent_name: str) -> AdapterResult:
        task = context.task
        payload = {
            "task": self._build_prompt(context),
            "runtime": self.runtime,
            "agentId": agent_name,
            "mode": "run",
            "timeoutSeconds": self.timeout_sec,
            "metadata": {
                "agentflow": {
                    "taskId": task.id,
                    "project": task.project,
                    "status": task.status,
                    "source": task.source,
                    "externalId": task.external_id,
                    "prUrl": task.pr_url,
                }
            },
        }

        headers = {"Content-Type": "application/json"}
        if self.api_token:
            headers["Authorization"] = f"Bearer {self.api_token}"
        req = urllib.request.Request(
            f"{self.gateway_url}/api/sessions",
            data=json.dumps(payload).encode("utf-8"),
            headers=headers,
            method="POST",
        )

        try:
            with urllib.request.urlopen(req, timeout=self.timeout_sec) as resp:
                raw = resp.read()
        except urllib.error.URLError as exc:
            return AdapterResult(
                success=False,
                note=f"openclaw dispatch failed: {exc}",
                to_status="blocked",
            )

        try:
            result = json.loads(raw.decode("utf-8")) if raw else {}
        except json.JSONDecodeError:
            return AdapterResult(success=False, note="openclaw returned non-JSON response", to_status="blocked")

        status = str(result.get("status", "")).lower()
        summary = str(result.get("summary") or result.get("message") or "openclaw execution finished")
        pr_url = result.get("pr_url")
        pr_url_s = str(pr_url) if pr_url else None

        success = status in {"completed", "success", "succeeded", "passed"}
        if success:
            if pr_url_s:
                return AdapterResult(success=True, note=f"{summary}; pr={pr_url_s}", to_status="pr_open")
            return AdapterResult(success=True, note=summary, to_status="pr_ready")
        return AdapterResult(success=False, note=summary, to_status="blocked")

    def _build_prompt(self, context: AdapterContext) -> str:
        task = context.task
        parts = [
            "You are executing one AgentFlow task.",
            f"Task ID: {task.id}",
            f"Project: {task.project}",
            f"Title: {task.title}",
            f"Current Status: {task.status}",
            f"Priority/Impact/Effort: {task.priority}/{task.impact}/{task.effort}",
        ]
        if task.source:
            parts.append(f"Source: {task.source}")
        if task.external_id:
            parts.append(f"External ID: {task.external_id}")
        if task.description:
            parts.extend(["", "Description:", task.description])
        if context.repo_full_name:
            parts.append(f"Repository: {context.repo_full_name}")
        if context.previous_runs:
            parts.append("")
            parts.append("Previous Runs:")
            for run in context.previous_runs[:3]:
                run_id = run.get("id")
                status = run.get("status")
                summary = run.get("result_summary") or "-"
                parts.append(f"- run #{run_id} status={status} summary={summary}")
        if context.gate_profile:
            checks = context.gate_profile.get("required_checks")
            commands = context.gate_profile.get("commands")
            parts.append("")
            parts.append(f"Gate Required Checks: {checks}")
            parts.append(f"Gate Commands: {commands}")
        if task.pr_url:
            parts.append(f"Existing PR: {task.pr_url}")
        parts.extend(
            [
                "",
                "Expected output:",
                "1) Brief implementation summary",
                "2) Test/gate evidence",
                "3) PR URL if created",
                "4) Explicit final outcome: success or blocked with reason",
            ]
        )
        return "\n".join(parts)
