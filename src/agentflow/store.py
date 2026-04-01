from __future__ import annotations

import json
import sqlite3
import threading
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
ALLOWED_TRANSITIONS = {
    "pending": {"approved", "blocked", "skipped"},
    "approved": {"pending", "in_progress", "blocked", "skipped"},
    "in_progress": {"approved", "pr_ready", "blocked"},
    "pr_ready": {"approved", "pr_open", "blocked"},
    "pr_open": {"approved", "merged", "blocked"},
    "blocked": {"pending", "approved", "skipped"},
    "merged": set(),
    "skipped": set(),
}
STATUS_ALIASES = {"done": "merged"}


class _ManagedConnection(sqlite3.Connection):
    def __exit__(self, exc_type, exc_val, exc_tb):
        out = super().__exit__(exc_type, exc_val, exc_tb)
        self.close()
        return out


@dataclass
class Task:
    id: int
    project: str
    title: str
    description: str | None
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
        self._schema_ready = False
        self._schema_lock = threading.Lock()

    def connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, factory=_ManagedConnection)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=5000")
        if not self._schema_ready:
            with self._schema_lock:
                if not self._schema_ready:
                    ensure_schema(conn)
                    self._schema_ready = True
        return conn

    def create_project(self, name: str, repo_full_name: str | None) -> None:
        with self.connect() as conn:
            conn.execute(
                "INSERT INTO projects(name, repo_full_name) VALUES(?, ?) ON CONFLICT(name) DO UPDATE SET repo_full_name=excluded.repo_full_name",
                (name, repo_full_name),
            )

    def _project_id(self, conn: sqlite3.Connection, project: str) -> int:
        row = conn.execute("SELECT id FROM projects WHERE name = ?", (project,)).fetchone()
        if row is None:
            raise ValueError(f"Project '{project}' not found")
        return int(row["id"])

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
            project_id = self._project_id(conn, project)
            cur = conn.execute(
                """
                INSERT INTO tasks(project_id, title, description, priority, impact, effort, source, external_id)
                VALUES(?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (project_id, title, description, priority, impact, effort, source, external_id),
            )
            task_id = int(cur.lastrowid)
            conn.execute(
                "INSERT INTO status_history(task_id, from_status, to_status, note) VALUES(?, ?, ?, ?)",
                (task_id, None, "pending", "task created"),
            )
            return task_id

    def create_run(
        self,
        *,
        task_id: int,
        project: str,
        trigger_type: str,
        trigger_ref: str,
        adapter: str,
        agent_name: str,
        idempotency_key: str,
        workspace_ref: str | None = None,
    ) -> int:
        with self.connect() as conn:
            project_id = self._project_id(conn, project)
            task_row = conn.execute(
                """
                SELECT t.id
                FROM tasks t
                JOIN projects p ON p.id = t.project_id
                WHERE t.id = ? AND p.id = ?
                """,
                (task_id, project_id),
            ).fetchone()
            if task_row is None:
                raise ValueError(f"Task {task_id} not found in project '{project}'")

            cur = conn.execute(
                """
                INSERT INTO runs(
                    task_id, project_id, trigger_type, trigger_ref, adapter, agent_name,
                    workspace_ref, status, idempotency_key
                )
                VALUES(?, ?, ?, ?, ?, ?, ?, 'running', ?)
                """,
                (
                    task_id,
                    project_id,
                    trigger_type,
                    trigger_ref,
                    adapter,
                    agent_name,
                    workspace_ref,
                    idempotency_key,
                ),
            )
            return int(cur.lastrowid)

    def append_run_step(
        self,
        run_id: int,
        step_name: str,
        status: str,
        log_excerpt: str | None = None,
        error_code: str | None = None,
    ) -> int:
        with self.connect() as conn:
            cur = conn.execute(
                """
                INSERT INTO run_steps(run_id, step_name, status, log_excerpt, error_code)
                VALUES(?, ?, ?, ?, ?)
                """,
                (run_id, step_name, status, log_excerpt, error_code),
            )
            return int(cur.lastrowid)

    def finalize_run(
        self,
        run_id: int,
        status: str,
        *,
        gate_passed: bool,
        result_summary: str | None = None,
        error_code: str | None = None,
        error_detail: str | None = None,
    ) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                UPDATE runs
                SET status = ?,
                    gate_passed = ?,
                    result_summary = ?,
                    error_code = ?,
                    error_detail = ?,
                    finished_at = datetime('now')
                WHERE id = ?
                """,
                (
                    status,
                    1 if gate_passed else 0,
                    result_summary,
                    error_code,
                    error_detail,
                    run_id,
                ),
            )

    def list_runs(self, task_id: int) -> list[sqlite3.Row]:
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT id, task_id, project_id, trigger_type, trigger_ref, adapter, agent_name,
                       workspace_ref, status, gate_passed, result_summary, error_code, error_detail,
                       idempotency_key, started_at, finished_at
                FROM runs
                WHERE task_id = ?
                ORDER BY id DESC
                """,
                (task_id,),
            ).fetchall()
            return list(rows)

    def list_run_steps(self, run_id: int) -> list[sqlite3.Row]:
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT id, run_id, step_name, status, log_excerpt, error_code, started_at, ended_at
                FROM run_steps
                WHERE run_id = ?
                ORDER BY id ASC
                """,
                (run_id,),
            ).fetchall()
            return list(rows)

    def list_recent_runs(self, project: str, limit: int = 20) -> list[sqlite3.Row]:
        with self.connect() as conn:
            project_id = self._project_id(conn, project)
            rows = conn.execute(
                """
                SELECT r.id, r.task_id, t.title AS task_title, ? AS project,
                       r.trigger_type, r.trigger_ref, r.adapter, r.agent_name,
                       r.status, r.gate_passed, r.result_summary, r.error_code, r.error_detail,
                       r.idempotency_key, r.started_at, r.finished_at
                FROM runs r
                JOIN tasks t ON t.id = r.task_id
                WHERE r.project_id = ?
                ORDER BY r.id DESC
                LIMIT ?
                """,
                (project, project_id, limit),
            ).fetchall()
            return list(rows)

    def append_event(self, project: str, event: str, payload: dict[str, object]) -> int:
        with self.connect() as conn:
            project_id = self._project_id(conn, project)
            cur = conn.execute(
                """
                INSERT INTO events(project_id, event, payload)
                VALUES(?, ?, ?)
                """,
                (project_id, event, json.dumps(payload, ensure_ascii=False)),
            )
            return int(cur.lastrowid)

    def list_events_since(self, project: str, last_event_id: int, limit: int = 200) -> list[sqlite3.Row]:
        with self.connect() as conn:
            project_id = self._project_id(conn, project)
            rows = conn.execute(
                """
                SELECT e.id, p.name AS project, e.event, e.payload, e.created_at
                FROM events e
                JOIN projects p ON p.id = e.project_id
                WHERE e.project_id = ? AND e.id > ?
                ORDER BY e.id ASC
                LIMIT ?
                """,
                (project_id, max(0, int(last_event_id)), max(1, min(1000, int(limit)))),
            ).fetchall()
            return list(rows)

    def upsert_trigger(
        self,
        *,
        project: str,
        trigger_type: str,
        trigger_ref: str,
        idempotency_key: str,
        payload: str | None = None,
    ) -> int:
        with self.connect() as conn:
            project_id = self._project_id(conn, project)
            conn.execute(
                """
                INSERT INTO triggers(project_id, trigger_type, trigger_ref, idempotency_key, payload)
                VALUES(?, ?, ?, ?, ?)
                ON CONFLICT(idempotency_key) DO UPDATE SET
                    payload = excluded.payload,
                    triggered_at = datetime('now')
                """,
                (project_id, trigger_type, trigger_ref, idempotency_key, payload),
            )
            row = conn.execute(
                "SELECT id FROM triggers WHERE idempotency_key = ?",
                (idempotency_key,),
            ).fetchone()
            if row is None:
                raise ValueError("Trigger upsert failed")
            return int(row["id"])

    def get_trigger_by_key(self, idempotency_key: str) -> sqlite3.Row | None:
        with self.connect() as conn:
            row = conn.execute(
                """
                SELECT id, project_id, trigger_type, trigger_ref, idempotency_key, payload, triggered_at
                FROM triggers
                WHERE idempotency_key = ?
                """,
                (idempotency_key,),
            ).fetchone()
            return row

    def list_triggers(self, project: str | None = None) -> list[sqlite3.Row]:
        with self.connect() as conn:
            if project is None:
                rows = conn.execute(
                    """
                    SELECT tr.id, p.name AS project, tr.trigger_type, tr.trigger_ref,
                           tr.idempotency_key, tr.payload, tr.triggered_at
                    FROM triggers tr
                    JOIN projects p ON p.id = tr.project_id
                    ORDER BY tr.id DESC
                    """
                ).fetchall()
                return list(rows)

            project_id = self._project_id(conn, project)
            rows = conn.execute(
                """
                SELECT tr.id, ? AS project, tr.trigger_type, tr.trigger_ref,
                       tr.idempotency_key, tr.payload, tr.triggered_at
                FROM triggers tr
                WHERE tr.project_id = ?
                ORDER BY tr.id DESC
                """,
                (project, project_id),
            ).fetchall()
            return list(rows)

    def upsert_gate_profile(
        self,
        *,
        project: str,
        required_checks: list[str],
        commands: list[str],
        timeout_sec: int = 1800,
        retry_policy: dict[str, object] | None = None,
        artifact_policy: dict[str, object] | None = None,
    ) -> None:
        with self.connect() as conn:
            project_id = self._project_id(conn, project)
            conn.execute(
                """
                INSERT INTO gate_profiles(
                    project_id, required_checks, commands, timeout_sec, retry_policy, artifact_policy, updated_at
                )
                VALUES(?, ?, ?, ?, ?, ?, datetime('now'))
                ON CONFLICT(project_id) DO UPDATE SET
                    required_checks = excluded.required_checks,
                    commands = excluded.commands,
                    timeout_sec = excluded.timeout_sec,
                    retry_policy = excluded.retry_policy,
                    artifact_policy = excluded.artifact_policy,
                    updated_at = datetime('now')
                """,
                (
                    project_id,
                    json.dumps(required_checks),
                    json.dumps(commands),
                    timeout_sec,
                    json.dumps(retry_policy or {}),
                    json.dumps(artifact_policy or {}),
                ),
            )

    def get_gate_profile(self, project: str) -> dict[str, object] | None:
        with self.connect() as conn:
            project_id = self._project_id(conn, project)
            row = conn.execute(
                """
                SELECT required_checks, commands, timeout_sec, retry_policy, artifact_policy, updated_at
                FROM gate_profiles
                WHERE project_id = ?
                """,
                (project_id,),
            ).fetchone()
            if row is None:
                return None
            return {
                "required_checks": json.loads(row["required_checks"]),
                "commands": json.loads(row["commands"]),
                "timeout_sec": int(row["timeout_sec"]),
                "retry_policy": json.loads(row["retry_policy"]),
                "artifact_policy": json.loads(row["artifact_policy"]),
                "updated_at": row["updated_at"],
            }

    def _base_task_sql(self) -> str:
        return """
            SELECT t.id, p.name AS project, t.title, t.description, t.status, t.priority, t.impact, t.effort,
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

    def get_task(self, task_id: int) -> Task | None:
        with self.connect() as conn:
            row = conn.execute(self._base_task_sql() + " WHERE t.id = ?", (task_id,)).fetchone()
            if row is None:
                return None
            return Task(**dict(row))

    def list_status_history(self, task_id: int) -> list[sqlite3.Row]:
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT id, task_id, from_status, to_status, note, changed_at
                FROM status_history
                WHERE task_id = ?
                ORDER BY id DESC
                """,
                (task_id,),
            ).fetchall()
            return list(rows)

    def list_recent_status_history(self, project: str, limit: int = 50) -> list[sqlite3.Row]:
        with self.connect() as conn:
            project_id = self._project_id(conn, project)
            rows = conn.execute(
                """
                SELECT sh.id, sh.task_id, t.title AS task_title, ? AS project,
                       sh.from_status, sh.to_status, sh.note, sh.changed_at
                FROM status_history sh
                JOIN tasks t ON t.id = sh.task_id
                WHERE t.project_id = ?
                ORDER BY sh.id DESC
                LIMIT ?
                """,
                (project, project_id, limit),
            ).fetchall()
            return list(rows)

    def get_task_by_external(self, project: str, source: str, external_id: str) -> Task | None:
        with self.connect() as conn:
            row = conn.execute(
                self._base_task_sql()
                + " WHERE p.name = ? AND t.source = ? AND t.external_id = ? ORDER BY t.id DESC LIMIT 1",
                (project, source, external_id),
            ).fetchone()
            if row is None:
                return None
            return Task(**dict(row))

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

    def claim_task(self, task_id: int, project: str, agent: str, lease_minutes: int = 30) -> Task | None:
        with self.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute(
                """
                SELECT t.id, t.status
                FROM tasks t
                JOIN projects p ON p.id = t.project_id
                WHERE t.id = ?
                  AND p.name = ?
                  AND t.status IN ('pending', 'approved')
                  AND (t.lease_until IS NULL OR t.lease_until < datetime('now'))
                LIMIT 1
                """,
                (task_id, project),
            ).fetchone()
            if row is None:
                conn.commit()
                return None

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
        to_status = self._normalize_status(to_status)

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

    def move_task(self, task_id: int, to_status: str, note: str | None, force: bool = False) -> None:
        to_status = self._normalize_status(to_status)
    def move_task(self, task_id: int, to_status: str, note: str | None, force: bool = False) -> None:
        to_status = self._normalize_status(to_status)
        with self.connect() as conn:
            row = conn.execute("SELECT status FROM tasks WHERE id = ?", (task_id,)).fetchone()
            if row is None:
                raise ValueError(f"Task {task_id} not found")
            from_status = str(row["status"])
            if not force:
                self._validate_transition(from_status, to_status)
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

    def _validate_transition(self, from_status: str, to_status: str) -> None:
        next_set = ALLOWED_TRANSITIONS.get(from_status)
        if next_set is None:
            raise ValueError(f"Unknown current status: {from_status}")
        if to_status not in next_set:
            raise ValueError(f"Transition not allowed: {from_status} -> {to_status}")

    def _normalize_status(self, status: str) -> str:
        normalized = STATUS_ALIASES.get(status, status)
        if normalized not in STATUSES:
            valid = ", ".join(sorted(STATUSES))
            aliases = ", ".join(f"{k}->{v}" for k, v in sorted(STATUS_ALIASES.items()))
            raise ValueError(f"Invalid status: {status}. Valid statuses: {valid}. Aliases: {aliases}")
        return normalized

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

    def get_project_repo(self, project: str) -> str | None:
        with self.connect() as conn:
            row = conn.execute("SELECT repo_full_name FROM projects WHERE name = ?", (project,)).fetchone()
            if row is None:
                return None
            return str(row["repo_full_name"]) if row["repo_full_name"] else None
