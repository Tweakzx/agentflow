from __future__ import annotations

from collections import defaultdict
from pathlib import Path

from .store import Store


def export_markdown(store: Store, out_dir: str, project: str | None = None) -> list[str]:
    Path(out_dir).mkdir(parents=True, exist_ok=True)
    created: list[str] = []

    projects = [project] if project else list(store.projects())
    for project_name in projects:
        tasks = store.list_tasks(project_name)
        status_groups: dict[str, list] = defaultdict(list)
        for t in tasks:
            status_groups[t.status].append(t)

        out_path = Path(out_dir) / f"{project_name}-board.md"
        lines = [f"# {project_name} task board", ""]
        for status in ["pending", "approved", "in_progress", "pr_ready", "pr_open", "merged", "blocked", "skipped"]:
            lines.append(f"## {status}")
            group = status_groups.get(status, [])
            if not group:
                lines.append("(none)")
            else:
                for t in group:
                    ext = f" ({t.source}:{t.external_id})" if t.source and t.external_id else ""
                    lines.append(f"- [{t.id}] {t.title}{ext}")
            lines.append("")

        out_path.write_text("\n".join(lines), encoding="utf-8")
        created.append(str(out_path))

    return created


def build_dashboard_html(store: Store) -> str:
    statuses = ["pending", "approved", "in_progress", "pr_ready", "pr_open", "merged", "blocked", "skipped"]
    rows = []
    for project in store.projects():
        counts = store.status_counts(project)
        row = [str(counts.get(s, 0)) for s in statuses]
        rows.append((project, row))

    table_rows = "\n".join(
        f"<tr><td>{project}</td>{''.join(f'<td>{c}</td>' for c in cols)}</tr>" for project, cols in rows
    )

    return f"""<!doctype html>
<html>
<head>
<meta charset=\"utf-8\" />
<title>AgentFlow Dashboard</title>
<style>
body {{ font-family: 'Segoe UI', sans-serif; margin: 24px; color: #1b2430; background: linear-gradient(135deg, #f8fbff, #eef5ff); }}
.card {{ background: #fff; border-radius: 12px; padding: 20px; box-shadow: 0 8px 20px rgba(0,0,0,0.06); max-width: 1000px; }}
table {{ border-collapse: collapse; width: 100%; }}
th, td {{ border-bottom: 1px solid #e7edf5; padding: 8px 10px; text-align: left; }}
th {{ background: #f3f8ff; }}
</style>
</head>
<body>
<div class=\"card\">
<h1>AgentFlow Dashboard</h1>
<p>Generated from SQLite source of truth.</p>
<table>
<thead><tr><th>Project</th>{''.join(f'<th>{s}</th>' for s in statuses)}</tr></thead>
<tbody>{table_rows}</tbody>
</table>
</div>
</body>
</html>
"""
