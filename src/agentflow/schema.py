from __future__ import annotations

import sqlite3
from pathlib import Path

BOOTSTRAP_REVISION = "0001_bootstrap_schema"

LEGACY_SCHEMA_SQL = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS projects (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    repo_full_name TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS tasks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL,
    title TEXT NOT NULL,
    description TEXT,
    status TEXT NOT NULL DEFAULT 'todo',
    priority INTEGER NOT NULL DEFAULT 3 CHECK(priority BETWEEN 1 AND 5),
    impact INTEGER NOT NULL DEFAULT 3 CHECK(impact BETWEEN 1 AND 5),
    effort INTEGER NOT NULL DEFAULT 3 CHECK(effort BETWEEN 1 AND 5),
    source TEXT,
    external_id TEXT,
    branch TEXT,
    pr_url TEXT,
    assigned_agent TEXT,
    lease_until TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY(project_id) REFERENCES projects(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS status_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id INTEGER NOT NULL,
    from_status TEXT,
    to_status TEXT NOT NULL,
    note TEXT,
    changed_at TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY(task_id) REFERENCES tasks(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS links (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id INTEGER NOT NULL,
    kind TEXT NOT NULL,
    url TEXT NOT NULL,
    FOREIGN KEY(task_id) REFERENCES tasks(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id INTEGER NOT NULL,
    project_id INTEGER NOT NULL,
    trigger_type TEXT NOT NULL,
    trigger_ref TEXT NOT NULL,
    adapter TEXT NOT NULL,
    agent_name TEXT NOT NULL,
    workspace_ref TEXT,
    status TEXT NOT NULL DEFAULT 'running',
    gate_passed INTEGER NOT NULL DEFAULT 0,
    result_summary TEXT,
    error_code TEXT,
    error_detail TEXT,
    idempotency_key TEXT NOT NULL UNIQUE,
    started_at TEXT NOT NULL DEFAULT (datetime('now')),
    finished_at TEXT,
    FOREIGN KEY(task_id) REFERENCES tasks(id) ON DELETE CASCADE,
    FOREIGN KEY(project_id) REFERENCES projects(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS run_steps (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id INTEGER NOT NULL,
    step_name TEXT NOT NULL,
    status TEXT NOT NULL,
    log_excerpt TEXT,
    error_code TEXT,
    started_at TEXT NOT NULL DEFAULT (datetime('now')),
    ended_at TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY(run_id) REFERENCES runs(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS triggers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL,
    trigger_type TEXT NOT NULL,
    trigger_ref TEXT NOT NULL,
    idempotency_key TEXT NOT NULL UNIQUE,
    payload TEXT,
    triggered_at TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY(project_id) REFERENCES projects(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS gate_profiles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL UNIQUE,
    required_checks TEXT NOT NULL DEFAULT '[]',
    commands TEXT NOT NULL DEFAULT '[]',
    timeout_sec INTEGER NOT NULL DEFAULT 1800,
    retry_policy TEXT NOT NULL DEFAULT '{}',
    artifact_policy TEXT NOT NULL DEFAULT '{}',
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY(project_id) REFERENCES projects(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL,
    event TEXT NOT NULL,
    payload TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY(project_id) REFERENCES projects(id) ON DELETE CASCADE
);
"""


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _sqlite_url(db_path: str) -> str:
    resolved = Path(db_path).resolve().as_posix()
    return f"sqlite:///{resolved}"


def _bootstrap_legacy_schema(db_path: str) -> None:
    with sqlite3.connect(db_path) as conn:
        conn.executescript(LEGACY_SCHEMA_SQL)
        if not _column_exists(conn, "tasks", "assigned_agent"):
            conn.execute("ALTER TABLE tasks ADD COLUMN assigned_agent TEXT")
        if not _column_exists(conn, "tasks", "lease_until"):
            conn.execute("ALTER TABLE tasks ADD COLUMN lease_until TEXT")
        conn.executescript(
            """
            CREATE INDEX IF NOT EXISTS idx_tasks_project_status ON tasks(project_id, status);
            CREATE INDEX IF NOT EXISTS idx_tasks_project_priority ON tasks(project_id, priority DESC, impact DESC);
            CREATE INDEX IF NOT EXISTS idx_tasks_lease ON tasks(lease_until, assigned_agent);
            CREATE INDEX IF NOT EXISTS idx_runs_task_id ON runs(task_id);
            CREATE INDEX IF NOT EXISTS idx_runs_project_id ON runs(project_id);
            CREATE INDEX IF NOT EXISTS idx_run_steps_run_id ON run_steps(run_id);
            CREATE INDEX IF NOT EXISTS idx_triggers_project_id ON triggers(project_id);
            CREATE INDEX IF NOT EXISTS idx_events_project_id ON events(project_id, id);
            """
        )
        conn.execute(
            """
            UPDATE tasks
            SET status = CASE status
                WHEN 'pending' THEN 'todo'
                WHEN 'approved' THEN 'ready'
                WHEN 'pr_ready' THEN 'review'
                WHEN 'pr_open' THEN 'review'
                WHEN 'merged' THEN 'done'
                WHEN 'skipped' THEN 'dropped'
                WHEN 'triaged' THEN 'ready'
                ELSE status
            END
            """
        )
        conn.execute(
            """
            UPDATE status_history
            SET from_status = CASE from_status
                WHEN 'pending' THEN 'todo'
                WHEN 'approved' THEN 'ready'
                WHEN 'pr_ready' THEN 'review'
                WHEN 'pr_open' THEN 'review'
                WHEN 'merged' THEN 'done'
                WHEN 'skipped' THEN 'dropped'
                WHEN 'triaged' THEN 'ready'
                ELSE from_status
            END,
            to_status = CASE to_status
                WHEN 'pending' THEN 'todo'
                WHEN 'approved' THEN 'ready'
                WHEN 'pr_ready' THEN 'review'
                WHEN 'pr_open' THEN 'review'
                WHEN 'merged' THEN 'done'
                WHEN 'skipped' THEN 'dropped'
                WHEN 'triaged' THEN 'ready'
                ELSE to_status
            END
            """
        )
        conn.execute(
            "CREATE TABLE IF NOT EXISTS alembic_version (version_num VARCHAR(32) NOT NULL)"
        )
        conn.execute("DELETE FROM alembic_version")
        conn.execute("INSERT INTO alembic_version(version_num) VALUES(?)", (BOOTSTRAP_REVISION,))
        conn.commit()


def _column_exists(conn: sqlite3.Connection, table: str, column: str) -> bool:
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return any(row[1] == column for row in rows)


def ensure_schema(db_path: str) -> None:
    try:
        from alembic import command
        from alembic.config import Config
    except ImportError:
        _bootstrap_legacy_schema(db_path)
        return

    root = _repo_root()
    config = Config(str(root / "alembic.ini"))
    config.set_main_option("script_location", str(root / "migrations"))
    config.set_main_option("sqlalchemy.url", _sqlite_url(db_path))
    command.upgrade(config, "head")
