from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path

from agentflow.store import Store


class StoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        db = Path(self.tempdir.name) / "test.db"
        self.store = Store(str(db))

    def tearDown(self) -> None:
        self.tempdir.cleanup()

    def test_create_project_and_add_task(self) -> None:
        self.store.create_project("kthena", "volcano-sh/kthena")
        task_id = self.store.add_task(
            project="kthena",
            title="controller partition revision bug",
            description=None,
            priority=5,
            impact=5,
            effort=2,
            source="github",
            external_id="841",
        )

        tasks = self.store.list_tasks("kthena")
        self.assertEqual(task_id, tasks[0].id)
        self.assertEqual("controller partition revision bug", tasks[0].title)

    def test_next_task_ranking(self) -> None:
        self.store.create_project("demo", None)

        self.store.add_task(
            project="demo",
            title="high impact",
            description=None,
            priority=5,
            impact=5,
            effort=2,
            source=None,
            external_id=None,
        )
        self.store.add_task(
            project="demo",
            title="low impact",
            description=None,
            priority=3,
            impact=2,
            effort=4,
            source=None,
            external_id=None,
        )

        ranked = self.store.next_tasks("demo", 2)
        self.assertEqual("high impact", ranked[0].title)

    def test_claim_heartbeat_release(self) -> None:
        self.store.create_project("demo", None)
        self.store.add_task(
            project="demo",
            title="task-a",
            description=None,
            priority=5,
            impact=5,
            effort=2,
            source=None,
            external_id=None,
        )
        self.store.add_task(
            project="demo",
            title="task-b",
            description=None,
            priority=4,
            impact=4,
            effort=2,
            source=None,
            external_id=None,
        )

        claimed = self.store.claim_next_task("demo", "codex", lease_minutes=10)
        self.assertIsNotNone(claimed)
        assert claimed is not None
        self.assertEqual("in_progress", claimed.status)
        self.assertEqual("codex", claimed.assigned_agent)

        heartbeat_ok = self.store.heartbeat(claimed.id, "codex", lease_minutes=20)
        self.assertTrue(heartbeat_ok)

        wrong_release = self.store.release_claim(claimed.id, "other-agent", to_status="ready")
        self.assertFalse(wrong_release)

        release_ok = self.store.release_claim(claimed.id, "codex", to_status="ready")
        self.assertTrue(release_ok)

        tasks = self.store.list_tasks("demo")
        reset_task = [t for t in tasks if t.id == claimed.id][0]
        self.assertEqual("ready", reset_task.status)
        self.assertIsNone(reset_task.assigned_agent)

    def test_run_ledger_lifecycle(self) -> None:
        self.store.create_project("demo", "example/demo")
        task_id = self.store.add_task(
            project="demo",
            title="run-ledger-test",
            description=None,
            priority=5,
            impact=5,
            effort=2,
            source="github",
            external_id="9001",
        )

        run_id = self.store.create_run(
            task_id=task_id,
            project="demo",
            trigger_type="comment",
            trigger_ref="pr#12:comment#34",
            adapter="mock",
            agent_name="codex-a",
            idempotency_key="pr12-comment34",
        )
        self.store.append_run_step(run_id, "claim", "passed", "claimed task")
        self.store.finalize_run(run_id, "passed", gate_passed=True, result_summary="all checks passed")

        runs = self.store.list_runs(task_id)
        steps = self.store.list_run_steps(run_id)

        self.assertEqual(1, len(runs))
        self.assertEqual("passed", runs[0]["status"])
        self.assertTrue(bool(runs[0]["gate_passed"]))
        self.assertEqual(1, len(steps))
        self.assertEqual("claim", steps[0]["step_name"])

    def test_list_recent_runs(self) -> None:
        self.store.create_project("demo", "example/demo")
        task_id = self.store.add_task(
            project="demo",
            title="recent-runs-test",
            description=None,
            priority=4,
            impact=4,
            effort=2,
            source="github",
            external_id="9010",
        )
        run_id = self.store.create_run(
            task_id=task_id,
            project="demo",
            trigger_type="manual",
            trigger_ref="runner:mock",
            adapter="mock",
            agent_name="tester",
            idempotency_key="recent-runs-1",
        )
        self.store.finalize_run(run_id, "passed", gate_passed=True, result_summary="ok")

        runs = self.store.list_recent_runs("demo", limit=10)
        self.assertEqual(1, len(runs))
        self.assertEqual(task_id, int(runs[0]["task_id"]))
        self.assertEqual("recent-runs-test", runs[0]["task_title"])

    def test_list_recent_status_history(self) -> None:
        self.store.create_project("demo", "example/demo")
        task_id = self.store.add_task(
            project="demo",
            title="status-history-test",
            description=None,
            priority=3,
            impact=3,
            effort=2,
            source="github",
            external_id="9011",
        )
        self.store.move_task(task_id, "ready", "ready")

        events = self.store.list_recent_status_history("demo", limit=10)
        self.assertGreaterEqual(len(events), 2)
        self.assertEqual(task_id, int(events[0]["task_id"]))
        self.assertEqual("status-history-test", events[0]["task_title"])

    def test_done_status_transitions(self) -> None:
        self.store.create_project("demo", "example/demo")
        task_id = self.store.add_task(
            project="demo",
            title="done-alias",
            description=None,
            priority=3,
            impact=3,
            effort=2,
            source=None,
            external_id=None,
        )
        self.store.move_task(task_id, "ready", "ready")
        self.store.move_task(task_id, "in_progress", "work started")
        self.store.move_task(task_id, "review", "ready for review")
        self.store.move_task(task_id, "done", "finalized")
        task = self.store.get_task(task_id)
        assert task is not None
        self.assertEqual("done", task.status)

    def test_event_persistence(self) -> None:
        self.store.create_project("demo", "example/demo")
        first_id = self.store.append_event("demo", "task_update", {"task_id": 1, "status": "todo"})
        second_id = self.store.append_event("demo", "progress", {"task_id": 1, "step": "run"})
        self.assertLess(first_id, second_id)
        rows = self.store.list_events_since("demo", first_id, limit=10)
        self.assertEqual(1, len(rows))
        self.assertEqual("progress", rows[0]["event"])

    def test_terminal_status_cannot_reopen(self) -> None:
        self.store.create_project("demo", "example/demo")
        task_id = self.store.add_task(
            project="demo",
            title="terminal-state-test",
            description=None,
            priority=3,
            impact=3,
            effort=2,
            source=None,
            external_id=None,
        )
        self.store.move_task(task_id, "dropped", "out of scope")
        with self.assertRaisesRegex(ValueError, "Transition not allowed"):
            self.store.move_task(task_id, "todo", "reopen")

    def test_force_move_task_allows_manual_override(self) -> None:
        self.store.create_project("demo", "example/demo")
        task_id = self.store.add_task(
            project="demo",
            title="force-transition-test",
            description=None,
            priority=3,
            impact=3,
            effort=2,
            source=None,
            external_id=None,
        )
        self.store.move_task(task_id, "blocked", "manual block")
        self.store.move_task(task_id, "review", "manual recovery", force=True)
        task = self.store.get_task(task_id)
        assert task is not None
        self.assertEqual("review", task.status)

    def test_legacy_status_names_are_rejected(self) -> None:
        self.store.create_project("demo", "example/demo")
        task_id = self.store.add_task(
            project="demo",
            title="legacy-statuses",
            description=None,
            priority=3,
            impact=3,
            effort=2,
            source=None,
            external_id=None,
        )
        with self.assertRaisesRegex(ValueError, "Invalid status"):
            self.store.move_task(task_id, "approved", "legacy-ready")

    def test_add_task_sets_todo_even_if_legacy_table_default_is_pending(self) -> None:
        db_path = str(Path(self.tempdir.name) / "legacy-default.db")
        with sqlite3.connect(db_path) as conn:
            conn.executescript(
                """
                CREATE TABLE projects (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL UNIQUE,
                    repo_full_name TEXT,
                    created_at TEXT NOT NULL DEFAULT (datetime('now'))
                );
                CREATE TABLE tasks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    project_id INTEGER NOT NULL,
                    title TEXT NOT NULL,
                    description TEXT,
                    status TEXT NOT NULL DEFAULT 'pending',
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
                    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
                );
                CREATE TABLE status_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    task_id INTEGER NOT NULL,
                    from_status TEXT,
                    to_status TEXT NOT NULL,
                    note TEXT,
                    changed_at TEXT NOT NULL DEFAULT (datetime('now'))
                );
                """
            )
            conn.execute("INSERT INTO projects(name, repo_full_name) VALUES('demo', 'example/demo')")
            conn.commit()

        legacy_store = Store(db_path)
        task_id = legacy_store.add_task(
            project="demo",
            title="legacy-default-pending",
            description=None,
            priority=3,
            impact=3,
            effort=2,
            source=None,
            external_id=None,
        )
        task = legacy_store.get_task(task_id)
        assert task is not None
        self.assertEqual("todo", task.status)
        claimed = legacy_store.claim_next_task("demo", "worker-a")
        self.assertIsNotNone(claimed)

    def test_legacy_database_bootstraps_via_alembic(self) -> None:
        db_path = Path(self.tempdir.name) / "legacy-bootstrap.db"
        with sqlite3.connect(db_path) as conn:
            conn.executescript(
                """
                CREATE TABLE projects (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL UNIQUE,
                    repo_full_name TEXT,
                    created_at TEXT NOT NULL DEFAULT (datetime('now'))
                );
                CREATE TABLE tasks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    project_id INTEGER NOT NULL,
                    title TEXT NOT NULL,
                    description TEXT,
                    status TEXT NOT NULL DEFAULT 'pending',
                    priority INTEGER NOT NULL DEFAULT 3 CHECK(priority BETWEEN 1 AND 5),
                    impact INTEGER NOT NULL DEFAULT 3 CHECK(impact BETWEEN 1 AND 5),
                    effort INTEGER NOT NULL DEFAULT 3 CHECK(effort BETWEEN 1 AND 5),
                    source TEXT,
                    external_id TEXT,
                    branch TEXT,
                    pr_url TEXT,
                    created_at TEXT NOT NULL DEFAULT (datetime('now')),
                    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
                );
                CREATE TABLE status_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    task_id INTEGER NOT NULL,
                    from_status TEXT,
                    to_status TEXT NOT NULL,
                    note TEXT,
                    changed_at TEXT NOT NULL DEFAULT (datetime('now'))
                );
                INSERT INTO projects(name, repo_full_name) VALUES('demo', 'example/demo');
                INSERT INTO tasks(project_id, title, description, status, priority, impact, effort, source, external_id)
                VALUES(1, 'legacy-task', NULL, 'pending', 3, 3, 2, NULL, NULL);
                INSERT INTO status_history(task_id, from_status, to_status, note)
                VALUES(1, 'pending', 'approved', 'legacy state');
                """
            )
            conn.commit()

        store = Store(str(db_path))
        with store.connect() as conn:
            task = conn.execute("SELECT status, assigned_agent, lease_until FROM tasks WHERE id = 1").fetchone()
            assert task is not None
            self.assertEqual("todo", task["status"])
            self.assertIsNone(task["assigned_agent"])
            self.assertIsNone(task["lease_until"])
            history = conn.execute(
                "SELECT from_status, to_status FROM status_history WHERE task_id = 1 ORDER BY id ASC"
            ).fetchone()
            assert history is not None
            self.assertEqual(("todo", "ready"), (history["from_status"], history["to_status"]))
            version = conn.execute("SELECT version_num FROM alembic_version").fetchone()
            assert version is not None
            self.assertEqual("0001_bootstrap_schema", version["version_num"])

    def test_versioned_database_startup_does_not_rewrite_rows(self) -> None:
        db_path = Path(self.tempdir.name) / "versioned-no-rewrite.db"
        with sqlite3.connect(db_path) as conn:
            conn.executescript(
                """
                CREATE TABLE projects (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL UNIQUE,
                    repo_full_name TEXT,
                    created_at TEXT NOT NULL DEFAULT (datetime('now'))
                );
                CREATE TABLE tasks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    project_id INTEGER NOT NULL,
                    title TEXT NOT NULL,
                    description TEXT,
                    status TEXT NOT NULL DEFAULT 'pending',
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
                    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
                );
                CREATE TABLE status_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    task_id INTEGER NOT NULL,
                    from_status TEXT,
                    to_status TEXT NOT NULL,
                    note TEXT,
                    changed_at TEXT NOT NULL DEFAULT (datetime('now'))
                );
                CREATE TABLE alembic_version (
                    version_num VARCHAR(32) NOT NULL
                );
                INSERT INTO alembic_version(version_num) VALUES('0001_bootstrap_schema');
                INSERT INTO projects(name, repo_full_name) VALUES('demo', 'example/demo');
                INSERT INTO tasks(project_id, title, description, status, priority, impact, effort, source, external_id)
                VALUES(1, 'legacy-task', NULL, 'pending', 3, 3, 2, NULL, NULL);
                """
            )
            conn.commit()

        store = Store(str(db_path))
        with store.connect() as conn:
            task = conn.execute("SELECT status FROM tasks WHERE id = 1").fetchone()
            assert task is not None
            self.assertEqual("pending", task["status"])


if __name__ == "__main__":
    unittest.main()
