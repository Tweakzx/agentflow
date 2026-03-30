from __future__ import annotations

import argparse
from pathlib import Path

from .reports import build_dashboard_html, export_markdown
from .store import Store


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="agentflow", description="AgentFlow Hub CLI")
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

    p_next = sub.add_parser("next", help="Recommend next tasks")
    p_next.add_argument("--project", required=True)
    p_next.add_argument("--limit", type=int, default=5)

    p_move = sub.add_parser("move", help="Move task status")
    p_move.add_argument("task_id", type=int)
    p_move.add_argument("to_status")
    p_move.add_argument("--note")

    p_stats = sub.add_parser("stats", help="Show status counts")
    p_stats.add_argument("--project")

    p_export = sub.add_parser("export-md", help="Export project boards to Markdown")
    p_export.add_argument("--out", default="./exports")

    p_dashboard = sub.add_parser("dashboard", help="Generate HTML dashboard")
    p_dashboard.add_argument("--out", default="./dashboard.html")

    return parser


def _print_tasks(tasks) -> None:
    if not tasks:
        print("(no tasks)")
        return
    print("id  project  status       pri imp eff score  title")
    print("--  -------  -----------  --- --- --- -----  -----")
    for t in tasks:
        print(
            f"{t.id:<3} {t.project:<8} {t.status:<11}  {t.priority:<3} {t.impact:<3} {t.effort:<3} {t.score:<5.1f}  {t.title}"
        )


def main() -> None:
    parser = _parser()
    args = parser.parse_args()
    store = Store(args.db)

    if args.command == "init":
        # Schema creation happens on first connection.
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
        _print_tasks(tasks)
        return

    if args.command == "next":
        tasks = store.next_tasks(args.project, args.limit)
        _print_tasks(tasks)
        return

    if args.command == "move":
        store.move_task(args.task_id, args.to_status, args.note)
        print(f"task {args.task_id} moved to {args.to_status}")
        return

    if args.command == "stats":
        counts = store.status_counts(args.project)
        for k in sorted(counts):
            print(f"{k}: {counts[k]}")
        return

    if args.command == "export-md":
        created = export_markdown(store, args.out)
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


if __name__ == "__main__":
    main()
