from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from .schema import ensure_schema

STATUSES = {
    "pending",
    "approved",
    "in_progress",
    "pr_ready",
    "pr_open",
    "merged",
    "skipped",
    "blocked",
}

ACTIVE_STATUSES = {"pending", "approved", "in_progress", "pr_ready", "pr_open", "blocked"}


@dataclass
class Task:
    id: int
    project: str
    title: str
    status: str
    priority: int
    impact: int
    effort: int
    source: str | None
    external_id: str | None
    pr_url: str | None

    @property
    def score(self) -> float:
        # Higher is better: prioritize impact/priority and discount effort.
        return (self.priority * 2 + self.impact * 3) / max(1, self.effort)


class Store:
    def __init__(self, db_path: str) -> None:
        self.db_path = db_path
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)

    def connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        ensure_schema(conn)
        return conn

    def create_project(self, name: str, repo_full_name: str | None) -> None:
        with self.connect() as conn:
            conn.execute(
                "INSERT INTO projects(name, repo_full_name) VALUES(?, ?) ON CONFLICT(name) DO UPDATE SET repo_full_name=excluded.repo_full_name",
                (name, repo_full_name),
            )

    def add_task(
        self,
        *,
        project: str,
        title: str,
        description: str | None,
        priority: int,
        impact: int,
        effort: int,
        source: str | None,
        external_id: str | None,
    ) -> int:
        with self.connect() as conn:
            row = conn.execute("SELECT id FROM projects WHERE name = ?", (project,)).fetchone()
            if row is None:
                raise ValueError(f"Project '{project}' not found")
            cur = conn.execute(
                """
                INSERT INTO tasks(project_id, title, description, priority, impact, effort, source, external_id)
                VALUES(?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (row["id"], title, description, priority, impact, effort, source, external_id),
            )
            task_id = int(cur.lastrowid)
            conn.execute(
                "INSERT INTO status_history(task_id, from_status, to_status, note) VALUES(?, ?, ?, ?)",
                (task_id, None, "pending", "task created"),
            )
            return task_id

    def list_tasks(self, project: str | None = None) -> list[Task]:
        with self.connect() as conn:
            sql = """
            SELECT t.id, p.name AS project, t.title, t.status, t.priority, t.impact, t.effort,
                   t.source, t.external_id, t.pr_url
            FROM tasks t
            JOIN projects p ON p.id = t.project_id
            """
            args: tuple[str, ...] = ()
            if project:
                sql += " WHERE p.name = ?"
                args = (project,)
            sql += " ORDER BY t.updated_at DESC, t.id DESC"
            rows = conn.execute(sql, args).fetchall()
            return [Task(**dict(row)) for row in rows]

    def next_tasks(self, project: str, limit: int = 5) -> list[Task]:
        tasks = [t for t in self.list_tasks(project) if t.status in ACTIVE_STATUSES]
        tasks.sort(key=lambda t: (t.score, t.priority, t.impact), reverse=True)
        return tasks[:limit]

    def move_task(self, task_id: int, to_status: str, note: str | None) -> None:
        if to_status not in STATUSES:
            raise ValueError(f"Invalid status: {to_status}")
        with self.connect() as conn:
            row = conn.execute("SELECT status FROM tasks WHERE id = ?", (task_id,)).fetchone()
            if row is None:
                raise ValueError(f"Task {task_id} not found")
            from_status = row["status"]
            conn.execute(
                "UPDATE tasks SET status = ?, updated_at = datetime('now') WHERE id = ?",
                (to_status, task_id),
            )
            conn.execute(
                "INSERT INTO status_history(task_id, from_status, to_status, note) VALUES(?, ?, ?, ?)",
                (task_id, from_status, to_status, note),
            )

    def status_counts(self, project: str | None = None) -> dict[str, int]:
        with self.connect() as conn:
            sql = "SELECT status, COUNT(*) AS c FROM tasks"
            args: tuple[str, ...] = ()
            if project:
                sql = (
                    "SELECT t.status, COUNT(*) AS c FROM tasks t "
                    "JOIN projects p ON p.id=t.project_id WHERE p.name=?"
                )
                args = (project,)
            sql += " GROUP BY status"
            rows = conn.execute(sql, args).fetchall()
            return {row["status"]: int(row["c"]) for row in rows}

    def projects(self) -> Iterable[str]:
        with self.connect() as conn:
            rows = conn.execute("SELECT name FROM projects ORDER BY name").fetchall()
            for row in rows:
                yield str(row["name"])
