from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

from .adapters.registry import AdapterRegistry
from .console import serve_console
from .reports import build_dashboard_html, export_markdown
from .services.discovery import IssueDiscoveryService
from .services.runner import Runner
from .services.webhook import GithubCommentWebhookService
from .store import Store


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="agentflow", description="AgentFlow CLI")
    parser.add_argument("--db", default="./data/agentflow.db", help="SQLite DB path")

    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("init", help="Initialize database")

    p_project = sub.add_parser("create-project", help="Create or update project")
    p_project.add_argument("name")
    p_project.add_argument("--repo", dest="repo_full_name")

    p_add = sub.add_parser("add-task", help="Create task")
    p_add.add_argument("--project", required=True)
    p_add.add_argument("--title", required=True)
    p_add.add_argument("--description")
    p_add.add_argument("--priority", type=int, default=3)
    p_add.add_argument("--impact", type=int, default=3)
    p_add.add_argument("--effort", type=int, default=3)
    p_add.add_argument("--source")
    p_add.add_argument("--external-id")

    p_board = sub.add_parser("board", help="Show tasks")
    p_board.add_argument("--project")
    p_board.add_argument("--json", action="store_true")

    p_next = sub.add_parser("next", help="Recommend next tasks")
    p_next.add_argument("--project", required=True)
    p_next.add_argument("--limit", type=int, default=5)

    p_claim = sub.add_parser("claim-next", help="Atomically claim next task for an agent")
    p_claim.add_argument("--project", required=True)
    p_claim.add_argument("--agent", required=True)
    p_claim.add_argument("--lease-minutes", type=int, default=30)

    p_heartbeat = sub.add_parser("heartbeat", help="Extend lease on a claimed task")
    p_heartbeat.add_argument("task_id", type=int)
    p_heartbeat.add_argument("--agent", required=True)
    p_heartbeat.add_argument("--lease-minutes", type=int, default=30)

    p_release = sub.add_parser("release", help="Release a claimed task")
    p_release.add_argument("task_id", type=int)
    p_release.add_argument("--agent", required=True)
    p_release.add_argument("--to-status", default="ready")
    p_release.add_argument("--note")

    p_workers = sub.add_parser("workers", help="List in-progress tasks with assigned agents")
    p_workers.add_argument("--project")

    p_move = sub.add_parser("move", help="Move task status")
    p_move.add_argument("task_id", type=int)
    p_move.add_argument("to_status")
    p_move.add_argument("--project")
    p_move.add_argument("--note")

    p_stats = sub.add_parser("stats", help="Show status counts")
    p_stats.add_argument("--project")

    p_export = sub.add_parser("export-md", help="Export project boards to Markdown")
    p_export.add_argument("--out", default="./exports")
    p_export.add_argument("--project")

    p_dashboard = sub.add_parser("dashboard", help="Generate HTML dashboard")
    p_dashboard.add_argument("--out", default="./dashboard.html")

    p_serve = sub.add_parser("serve", help="Start interactive web console")
    p_serve.add_argument("--host", default="127.0.0.1")
    p_serve.add_argument("--port", type=int, default=8787)
    p_serve.add_argument("--github-webhook-secret")

    p_runs = sub.add_parser("runs", help="List runs for a task")
    p_runs.add_argument("--task-id", required=True, type=int)
    p_runs.add_argument("--json", action="store_true")

    p_detail = sub.add_parser("task-detail", help="Show one task with runs and status history (JSON)")
    p_detail.add_argument("--task-id", required=True, type=int)
    p_detail.add_argument("--json", action="store_true")

    p_recent_runs = sub.add_parser("recent-runs", help="List recent runs for a project")
    p_recent_runs.add_argument("--project", required=True)
    p_recent_runs.add_argument("--limit", type=int, default=20)
    p_recent_runs.add_argument("--json", action="store_true")

    p_audit = sub.add_parser("audit", help="List recent status transition events for a project")
    p_audit.add_argument("--project", required=True)
    p_audit.add_argument("--limit", type=int, default=50)
    p_audit.add_argument("--json", action="store_true")

    p_run_steps = sub.add_parser("run-steps", help="List run steps")
    p_run_steps.add_argument("run_id", type=int)
    p_run_steps.add_argument("--json", action="store_true")

    p_triggers = sub.add_parser("triggers", help="List trigger records")
    p_triggers.add_argument("--project")

    p_gate = sub.add_parser("gate-profile", help="Show gate profile for project")
    p_gate.add_argument("--project", required=True)

    sub.add_parser("adapters", help="List registered adapters")

    p_run_once = sub.add_parser("run-once", help="Claim and run one task through an adapter")
    p_run_once.add_argument("--project", required=True)
    p_run_once.add_argument("--adapter", default="mock")
    p_run_once.add_argument("--agent", required=True)
    p_run_once.add_argument("--lease-minutes", type=int, default=30)

    p_run_batch = sub.add_parser("run-batch", help="Run multiple sequential claims with generated agent names")
    p_run_batch.add_argument("--project", required=True)
    p_run_batch.add_argument("--adapter", default="mock")
    p_run_batch.add_argument("--agent-prefix", default="worker")
    p_run_batch.add_argument("--count", type=int, default=3)
    p_run_batch.add_argument("--lease-minutes", type=int, default=30)

    p_discovery = sub.add_parser("discover-issues", help="Ingest scheduled issue discovery payload")
    p_discovery.add_argument("--project", required=True)
    p_discovery.add_argument("--from-file", required=True, dest="from_file")

    p_sync_issues = sub.add_parser("sync-issues", help="Fetch GitHub issues and ingest into AgentFlow")
    p_sync_issues.add_argument("--project", required=True)
    p_sync_issues.add_argument("--repo", required=True, help="GitHub repo in owner/name form")
    p_sync_issues.add_argument("--state", default="open", choices=["open", "closed", "all"])
    p_sync_issues.add_argument("--label", help="Optional GitHub label filter")
    p_sync_issues.add_argument("--limit", type=int, default=20)
    p_sync_issues.add_argument("--priority", type=int, default=4)
    p_sync_issues.add_argument("--impact", type=int, default=4)
    p_sync_issues.add_argument("--effort", type=int, default=2)
    p_sync_issues.add_argument("--token", help="GitHub token (or use GITHUB_TOKEN env)")

    p_comment = sub.add_parser("handle-comment", help="Handle GitHub PR/issue comment webhook payload")
    p_comment.add_argument("--project", required=True)
    p_comment.add_argument("--payload-file", required=True)
    p_comment.add_argument("--adapter", default="mock")
    p_comment.add_argument("--agent", required=True)

    # Also accept `--db` after subcommands for compatibility with README examples.
    # Use SUPPRESS so subparser defaults don't override a top-level `--db` value.
    for child in sub.choices.values():
        child.add_argument("--db", dest="db", default=argparse.SUPPRESS, help=argparse.SUPPRESS)

    return parser


def _print_tasks(tasks) -> None:
    if not tasks:
        print("(no tasks)")
        return
    print("id  project  status       pri imp eff score  agent         lease_until           title")
    print("--  -------  -----------  --- --- --- -----  ------------  -------------------  -----")
    for t in tasks:
        agent = t.assigned_agent or "-"
        lease = t.lease_until or "-"
        print(
            f"{t.id:<3} {t.project:<8} {t.status:<11}  {t.priority:<3} {t.impact:<3} {t.effort:<3} {t.score:<5.1f}  {agent:<12}  {lease:<19}  {t.title}"
        )


def _task_to_dict(task) -> dict:
    if hasattr(task, "__dataclass_fields__"):
        return dict(task.__dict__)
    return dict(task)


def main() -> None:
    parser = _parser()
    args = parser.parse_args()
    store = Store(args.db)
    registry = AdapterRegistry()
    runner = Runner(store, registry)
    discovery = IssueDiscoveryService(store)
    webhook = GithubCommentWebhookService(store, runner)

    if args.command == "init":
        with store.connect():
            pass
        print(f"initialized: {args.db}")
        return

    if args.command == "create-project":
        store.create_project(args.name, args.repo_full_name)
        print(f"project ready: {args.name}")
        return

    if args.command == "add-task":
        task_id = store.add_task(
            project=args.project,
            title=args.title,
            description=args.description,
            priority=args.priority,
            impact=args.impact,
            effort=args.effort,
            source=args.source,
            external_id=args.external_id,
        )
        print(f"task created: {task_id}")
        return

    if args.command == "board":
        tasks = store.list_tasks(args.project)
        if getattr(args, "json", False):
            print(json.dumps([_task_to_dict(t) for t in tasks], ensure_ascii=False, indent=2))
            return
        _print_tasks(tasks)
        return

    if args.command == "next":
        tasks = store.next_tasks(args.project, args.limit)
        _print_tasks(tasks)
        return

    if args.command == "claim-next":
        task = store.claim_next_task(args.project, args.agent, args.lease_minutes)
        if task is None:
            print("no claimable task")
        else:
            run_id = store.create_run(
                task_id=task.id,
                project=args.project,
                trigger_type="manual",
                trigger_ref="cli:claim-next",
                adapter="manual",
                agent_name=args.agent,
                idempotency_key=f"{args.project}:{task.id}:claim-next:{args.agent}:{time.time_ns()}",
            )
            store.append_run_step(run_id, "claim", "passed", f"claimed by {args.agent} via cli")
            _print_tasks([task])
        return

    if args.command == "heartbeat":
        ok = store.heartbeat(args.task_id, args.agent, args.lease_minutes)
        print("heartbeat ok" if ok else "heartbeat ignored (not owner or not in_progress)")
        return

    if args.command == "release":
        ok = store.release_claim(args.task_id, args.agent, args.to_status, args.note)
        print("released" if ok else "release ignored (not owner)")
        return

    if args.command == "workers":
        tasks = store.list_in_progress(args.project)
        _print_tasks(tasks)
        return

    if args.command == "move":
        try:
            if args.project:
                task = store.get_task(args.task_id)
                if task is None:
                    raise ValueError(f"Task {args.task_id} not found")
                if task.project != args.project:
                    raise ValueError(
                        f"Task {args.task_id} belongs to project '{task.project}', not '{args.project}'"
                    )
            store.move_task(args.task_id, args.to_status, args.note)
        except ValueError as exc:
            print(f"error: {exc}", file=sys.stderr)
            raise SystemExit(1) from exc
        print(f"task {args.task_id} moved to {args.to_status}")
        return

    if args.command == "stats":
        counts = store.status_counts(args.project)
        for k in sorted(counts):
            print(f"{k}: {counts[k]}")
        return

    if args.command == "export-md":
        created = export_markdown(store, args.out, project=args.project)
        if not created:
            print("no projects found")
        for path in created:
            print(path)
        return

    if args.command == "dashboard":
        html = build_dashboard_html(store)
        out_path = Path(args.out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(html, encoding="utf-8")
        print(f"dashboard written: {out_path}")
        return

    if args.command == "serve":
        serve_console(args.host, args.port, args.db, github_webhook_secret=args.github_webhook_secret)
        return

    if args.command == "runs":
        rows = store.list_runs(args.task_id)
        if getattr(args, "json", False):
            print(json.dumps([dict(r) for r in rows], ensure_ascii=False, indent=2))
            return
        if not rows:
            print("(no runs)")
            return
        for row in rows:
            print(
                f"{row['id']} task={row['task_id']} status={row['status']} "
                f"gate_passed={row['gate_passed']} adapter={row['adapter']} agent={row['agent_name']}"
            )
        return

    if args.command == "task-detail":
        task = store.get_task(args.task_id)
        if task is None:
            print("(task not found)")
            return
        runs = [dict(r) for r in store.list_runs(args.task_id)]
        history = [dict(h) for h in store.list_status_history(args.task_id)]
        for run in runs:
            run["steps"] = [dict(s) for s in store.list_run_steps(int(run["id"]))]
        payload = {"task": _task_to_dict(task), "runs": runs, "history": history}
        if getattr(args, "json", False):
            print(json.dumps(payload, ensure_ascii=False, indent=2))
            return
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return

    if args.command == "recent-runs":
        rows = store.list_recent_runs(args.project, limit=max(1, min(200, int(args.limit))))
        if getattr(args, "json", False):
            print(json.dumps([dict(r) for r in rows], ensure_ascii=False, indent=2))
            return
        if not rows:
            print("(no runs)")
            return
        for row in rows:
            print(
                f"{row['id']} task={row['task_id']} status={row['status']} "
                f"gate_passed={row['gate_passed']} adapter={row['adapter']} agent={row['agent_name']}"
            )
        return

    if args.command == "audit":
        rows = store.list_recent_status_history(args.project, limit=max(1, min(200, int(args.limit))))
        if getattr(args, "json", False):
            print(json.dumps([dict(r) for r in rows], ensure_ascii=False, indent=2))
            return
        if not rows:
            print("(no events)")
            return
        for row in rows:
            print(
                f"{row['id']} task={row['task_id']} from={row['from_status'] or '-'} "
                f"to={row['to_status']} note={row['note'] or '-'}"
            )
        return

    if args.command == "run-steps":
        rows = store.list_run_steps(args.run_id)
        if getattr(args, "json", False):
            print(json.dumps([dict(r) for r in rows], ensure_ascii=False, indent=2))
            return
        if not rows:
            print("(no run steps)")
            return
        for row in rows:
            print(
                f"{row['id']} run={row['run_id']} step={row['step_name']} status={row['status']} "
                f"log={row['log_excerpt'] or '-'}"
            )
        return

    if args.command == "triggers":
        rows = store.list_triggers(args.project)
        if not rows:
            print("(no triggers)")
            return
        for row in rows:
            print(
                f"{row['id']} project={row['project']} type={row['trigger_type']} "
                f"ref={row['trigger_ref']} key={row['idempotency_key']}"
            )
        return

    if args.command == "gate-profile":
        profile = store.get_gate_profile(args.project)
        if profile is None:
            print("(no gate profile)")
            return
        print(f"project={args.project}")
        print(f"required_checks={profile['required_checks']}")
        print(f"commands={profile['commands']}")
        print(f"timeout_sec={profile['timeout_sec']}")
        return

    if args.command == "adapters":
        for name in registry.names():
            print(name)
        return

    if args.command == "run-once":
        record = runner.run_once(args.project, args.adapter, args.agent, lease_minutes=args.lease_minutes)
        if record.task is None:
            print(record.message)
            return
        _print_tasks([record.task])
        print(record.message)
        return

    if args.command == "run-batch":
        records = runner.run_batch(
            args.project,
            args.adapter,
            args.agent_prefix,
            args.count,
            lease_minutes=args.lease_minutes,
        )
        tasks = [r.task for r in records if r.task is not None]
        if tasks:
            _print_tasks(tasks)
        else:
            print("(no tasks)")
        for r in records:
            print(r.message)
        return

    if args.command == "discover-issues":
        payload = json.loads(Path(args.from_file).read_text(encoding="utf-8"))
        if not isinstance(payload, list):
            raise ValueError("discover-issues payload must be a JSON array")
        result = discovery.ingest_issues(args.project, payload)
        print(f"created={result.created} skipped={result.skipped}")
        return

    if args.command == "sync-issues":
        limit = max(1, min(100, int(args.limit)))
        token = args.token or os.environ.get("GITHUB_TOKEN")
        query = {"state": args.state, "per_page": str(limit), "sort": "created", "direction": "desc"}
        if args.label:
            query["labels"] = args.label
        url = f"https://api.github.com/repos/{args.repo}/issues?{urllib.parse.urlencode(query)}"
        headers = {"Accept": "application/vnd.github+json", "User-Agent": "agentflow-sync-issues"}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        req = urllib.request.Request(url, headers=headers, method="GET")
        with urllib.request.urlopen(req, timeout=30) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
        if not isinstance(payload, list):
            raise ValueError("GitHub issues response must be a JSON array")
        normalized = []
        for item in payload:
            if not isinstance(item, dict):
                continue
            if "pull_request" in item:
                continue
            number = item.get("number")
            title = item.get("title")
            if not number or not title:
                continue
            normalized.append(
                {
                    "number": number,
                    "title": title,
                    "body": item.get("body"),
                    "priority": args.priority,
                    "impact": args.impact,
                    "effort": args.effort,
                }
            )
        result = discovery.ingest_issues(args.project, normalized)
        print(f"fetched={len(normalized)} created={result.created} skipped={result.skipped}")
        return

    if args.command == "handle-comment":
        payload = json.loads(Path(args.payload_file).read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("handle-comment payload must be a JSON object")
        result = webhook.handle_pr_comment(
            project=args.project,
            payload=payload,
            adapter=args.adapter,
            agent_name=args.agent,
        )
        print(
            f"accepted={result.accepted} duplicate={result.duplicate} "
            f"run_success={result.run_success} message={result.message}"
        )
        return


if __name__ == "__main__":
    main()
