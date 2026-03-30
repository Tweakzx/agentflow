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
CLAIMABLE_STATUSES = {"pending", "approved"}


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
    assigned_agent: str | None
    lease_until: str | None

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

    def _base_task_sql(self) -> str:
        return """
            SELECT t.id, p.name AS project, t.title, t.status, t.priority, t.impact, t.effort,
                   t.source, t.external_id, t.pr_url, t.assigned_agent, t.lease_until
            FROM tasks t
            JOIN projects p ON p.id = t.project_id
        """

    def list_tasks(self, project: str | None = None) -> list[Task]:
        with self.connect() as conn:
            sql = self._base_task_sql()
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

    def claim_next_task(self, project: str, agent: str, lease_minutes: int = 30) -> Task | None:
        with self.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute(
                """
                SELECT t.id, t.status
                FROM tasks t
                JOIN projects p ON p.id = t.project_id
                WHERE p.name = ?
                  AND t.status IN ('pending', 'approved')
                  AND (t.lease_until IS NULL OR t.lease_until < datetime('now'))
                ORDER BY ((t.priority * 2.0 + t.impact * 3.0) / CASE WHEN t.effort <= 0 THEN 1 ELSE t.effort END) DESC,
                         t.priority DESC,
                         t.impact DESC,
                         t.updated_at ASC,
                         t.id ASC
                LIMIT 1
                """,
                (project,),
            ).fetchone()
            if row is None:
                conn.commit()
                return None

            task_id = int(row["id"])
            from_status = str(row["status"])
            conn.execute(
                """
                UPDATE tasks
                SET status = 'in_progress',
                    assigned_agent = ?,
                    lease_until = datetime('now', ?),
                    updated_at = datetime('now')
                WHERE id = ?
                """,
                (agent, f"+{lease_minutes} minutes", task_id),
            )
            conn.execute(
                "INSERT INTO status_history(task_id, from_status, to_status, note) VALUES(?, ?, ?, ?)",
                (task_id, from_status, "in_progress", f"claimed by {agent}"),
            )
            task = conn.execute(self._base_task_sql() + " WHERE t.id = ?", (task_id,)).fetchone()
            conn.commit()
            return Task(**dict(task)) if task else None

    def heartbeat(self, task_id: int, agent: str, lease_minutes: int = 30) -> bool:
        with self.connect() as conn:
            cur = conn.execute(
                """
                UPDATE tasks
                SET lease_until = datetime('now', ?),
                    updated_at = datetime('now')
                WHERE id = ?
                  AND assigned_agent = ?
                  AND status = 'in_progress'
                """,
                (f"+{lease_minutes} minutes", task_id, agent),
            )
            return cur.rowcount > 0

    def release_claim(self, task_id: int, agent: str, to_status: str = "approved", note: str | None = None) -> bool:
        if to_status not in STATUSES:
            raise ValueError(f"Invalid status: {to_status}")

        with self.connect() as conn:
            row = conn.execute(
                "SELECT status FROM tasks WHERE id = ? AND assigned_agent = ?",
                (task_id, agent),
            ).fetchone()
            if row is None:
                return False

            from_status = str(row["status"])
            conn.execute(
                """
                UPDATE tasks
                SET status = ?,
                    assigned_agent = NULL,
                    lease_until = NULL,
                    updated_at = datetime('now')
                WHERE id = ?
                """,
                (to_status, task_id),
            )
            conn.execute(
                "INSERT INTO status_history(task_id, from_status, to_status, note) VALUES(?, ?, ?, ?)",
                (task_id, from_status, to_status, note or f"released by {agent}"),
            )
            return True

    def move_task(self, task_id: int, to_status: str, note: str | None) -> None:
        if to_status not in STATUSES:
            raise ValueError(f"Invalid status: {to_status}")
        with self.connect() as conn:
            row = conn.execute("SELECT status FROM tasks WHERE id = ?", (task_id,)).fetchone()
            if row is None:
                raise ValueError(f"Task {task_id} not found")
            from_status = row["status"]
            conn.execute(
                """
                UPDATE tasks
                SET status = ?,
                    assigned_agent = CASE WHEN ? IN ('merged', 'skipped', 'blocked', 'approved', 'pending', 'pr_ready', 'pr_open') THEN NULL ELSE assigned_agent END,
                    lease_until = CASE WHEN ? IN ('merged', 'skipped', 'blocked', 'approved', 'pending', 'pr_ready', 'pr_open') THEN NULL ELSE lease_until END,
                    updated_at = datetime('now')
                WHERE id = ?
                """,
                (to_status, to_status, to_status, task_id),
            )
            conn.execute(
                "INSERT INTO status_history(task_id, from_status, to_status, note) VALUES(?, ?, ?, ?)",
                (task_id, from_status, to_status, note),
            )

    def list_in_progress(self, project: str | None = None) -> list[Task]:
        with self.connect() as conn:
            sql = self._base_task_sql() + " WHERE t.status = 'in_progress'"
            args: tuple[str, ...] = ()
            if project:
                sql += " AND p.name = ?"
                args = (project,)
            sql += " ORDER BY t.lease_until ASC, t.id ASC"
            rows = conn.execute(sql, args).fetchall()
            return [Task(**dict(row)) for row in rows]

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
