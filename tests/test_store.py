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
        self.assertEqual("task", tasks[0].issue_type)
        self.assertEqual("medium", tasks[0].risk_level)

    def test_add_task_accepts_jira_lite_issue_fields(self) -> None:
        self.store.create_project("demo", "example/demo")
        task_id = self.store.add_task(
            project="demo",
            title="approve external publish",
            description="agent needs to post a summary",
            issue_type="incident",
            priority=5,
            impact=5,
            effort=2,
            success_criteria="human approval is recorded before posting",
            risk_level="critical",
            reporter="ops-lead",
            environment="prod",
            source="manual",
            external_id="approval-1",
        )

        task = self.store.get_task(task_id)
        assert task is not None
        self.assertEqual("incident", task.issue_type)
        self.assertEqual("critical", task.risk_level)
        self.assertEqual("ops-lead", task.reporter)
        self.assertEqual("prod", task.environment)
        self.assertEqual("human approval is recorded before posting", task.success_criteria)

    def test_task_dependencies_are_project_scoped(self) -> None:
        self.store.create_project("demo", "example/demo")
        blocker_id = self.store.add_task(
            project="demo",
            title="finish auth migration",
            description=None,
            priority=4,
            impact=4,
            effort=3,
            source=None,
            external_id=None,
        )
        blocked_id = self.store.add_task(
            project="demo",
            title="ship dashboard",
            description=None,
            priority=4,
            impact=4,
            effort=2,
            source=None,
            external_id=None,
        )

        dep_id = self.store.add_task_dependency(blocked_id, blocker_id, "depends_on")
        deps = self.store.list_task_dependencies(blocked_id)

        self.assertGreater(dep_id, 0)
        self.assertEqual(1, len(deps))
        self.assertEqual(blocked_id, int(deps[0]["blocked_task_id"]))
        self.assertEqual(blocker_id, int(deps[0]["blocking_task_id"]))
        self.assertEqual("depends_on", deps[0]["kind"])

    def test_agent_native_statuses_can_flow_through_approval_and_failure(self) -> None:
        self.store.create_project("demo", "example/demo")
        task_id = self.store.add_task(
            project="demo",
            title="approval task",
            description=None,
            priority=3,
            impact=3,
            effort=2,
            source=None,
            external_id=None,
        )

        self.store.move_task(task_id, "ready", "ready")
        self.store.move_task(task_id, "in_progress", "claimed")
        self.store.move_task(task_id, "waiting_for_approval", "needs approval")
        task = self.store.get_task(task_id)
        assert task is not None
        self.assertEqual("waiting_for_approval", task.status)

        self.store.move_task(task_id, "failed", "approval timed out")
        self.store.move_task(task_id, "ready", "retry")
        task = self.store.get_task(task_id)
        assert task is not None
        self.assertEqual("ready", task.status)

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

    def test_store_connections_enable_foreign_keys(self) -> None:
        with self.store.connect() as conn:
            self.assertEqual(1, int(conn.execute("PRAGMA foreign_keys").fetchone()[0]))

    def test_append_ledger_event_and_list_task_timeline(self) -> None:
        self.store.create_project("demo", "example/demo")
        task_id = self.store.add_task(
            project="demo",
            title="ledger-event-test",
            description=None,
            priority=3,
            impact=3,
            effort=3,
            source="manual",
            external_id=None,
        )
        run_id = self.store.create_run(
            task_id=task_id,
            project="demo",
            trigger_type="manual",
            trigger_ref="cli:test",
            adapter="mock",
            agent_name="codex-a",
            idempotency_key="ledger-event-test-run",
        )

        event_id = self.store.append_ledger_event(
            project="demo",
            task_id=task_id,
            run_id=run_id,
            trigger_id=None,
            parent_event_id=None,
            event_family="execution",
            event_type="run.started",
            actor_type="agent",
            actor_id="codex-a",
            source_type="manual",
            source_ref="cli:test",
            status_from="ready",
            status_to="in_progress",
            run_status_from=None,
            run_status_to="running",
            severity="info",
            summary="Run started for task #1",
            evidence={"step_name": "claim"},
            next_action={"recommended": "observe"},
            context={"adapter": "mock"},
            idempotency_key="ledger-event-test-event",
        )

        task_rows = self.store.list_task_timeline(task_id, limit=10)
        self.assertEqual(event_id, int(task_rows[0]["id"]))
        self.assertEqual("run.started", task_rows[0]["event_type"])
        self.assertEqual({"step_name": "claim"}, task_rows[0]["evidence"])
        self.assertEqual({"recommended": "observe"}, task_rows[0]["next_action"])
        self.assertEqual({"adapter": "mock"}, task_rows[0]["context"])
        self.assertNotIn("evidence_json", task_rows[0])
        self.assertNotIn("next_action_json", task_rows[0])
        self.assertNotIn("context_json", task_rows[0])

    def test_ledger_event_queries_cover_project_run_and_audit_views(self) -> None:
        self.store.create_project("demo", "example/demo")
        task_id = self.store.add_task(
            project="demo",
            title="ledger-event-queries",
            description=None,
            priority=4,
            impact=4,
            effort=2,
            source="manual",
            external_id=None,
        )
        run_id = self.store.create_run(
            task_id=task_id,
            project="demo",
            trigger_type="manual",
            trigger_ref="cli:test",
            adapter="mock",
            agent_name="codex-b",
            idempotency_key="ledger-event-queries-run",
        )
        self.store.append_ledger_event(
            project="demo",
            task_id=task_id,
            run_id=run_id,
            trigger_id=None,
            parent_event_id=None,
            event_family="feedback",
            event_type="progress.reported",
            actor_type="human",
            actor_id="reviewer",
            source_type="manual",
            source_ref="cli:test",
            status_from="in_progress",
            status_to="in_progress",
            run_status_from="running",
            run_status_to="running",
            severity="info",
            summary="Progress noted",
            evidence={"note": "keep going"},
            next_action={"recommended": "continue"},
            context={"channel": "cli"},
            idempotency_key="ledger-event-queries-event",
        )

        project_rows = self.store.list_project_events("demo", after_id=0, limit=10)
        run_rows = self.store.list_run_timeline(run_id, limit=10)
        audit_rows = self.store.list_project_audit_events("demo", limit=10)

        self.assertEqual(1, len(project_rows))
        self.assertEqual(1, len(run_rows))
        self.assertEqual(1, len(audit_rows))
        self.assertEqual("progress.reported", project_rows[0]["event_type"])
        self.assertEqual("progress.reported", run_rows[0]["event_type"])
        self.assertEqual("progress.reported", audit_rows[0]["event_type"])
        self.assertEqual({"note": "keep going"}, project_rows[0]["evidence"])

    def test_ledger_event_rejects_invalid_and_cross_project_references(self) -> None:
        self.store.create_project("demo", "example/demo")
        task_id = self.store.add_task(
            project="demo",
            title="reference-test",
            description=None,
            priority=3,
            impact=3,
            effort=3,
            source="manual",
            external_id=None,
        )
        run_id = self.store.create_run(
            task_id=task_id,
            project="demo",
            trigger_type="manual",
            trigger_ref="cli:test",
            adapter="mock",
            agent_name="codex-c",
            idempotency_key="reference-test-run",
        )

        with self.assertRaisesRegex(ValueError, "Task 999999 not found"):
            self.store.append_ledger_event(
                project="demo",
                task_id=999999,
                run_id=None,
                trigger_id=None,
                parent_event_id=None,
                event_family="execution",
                event_type="run.started",
                actor_type="system",
                actor_id=None,
                source_type=None,
                source_ref=None,
                status_from=None,
                status_to=None,
                run_status_from=None,
                run_status_to=None,
                severity="info",
                summary="missing task",
                evidence=None,
                next_action=None,
                context=None,
                idempotency_key="missing-task-event",
            )

        self.store.create_project("other", "example/other")
        other_task_id = self.store.add_task(
            project="other",
            title="cross-project-task",
            description=None,
            priority=3,
            impact=3,
            effort=3,
            source="manual",
            external_id=None,
        )
        other_run_id = self.store.create_run(
            task_id=other_task_id,
            project="other",
            trigger_type="manual",
            trigger_ref="cli:other",
            adapter="mock",
            agent_name="codex-d",
            idempotency_key="cross-project-run",
        )
        other_trigger_id = self.store.upsert_trigger(
            project="other",
            trigger_type="manual",
            trigger_ref="cli:other",
            idempotency_key="cross-project-trigger",
        )

        with self.assertRaisesRegex(ValueError, "Run .* does not belong to project"):
            self.store.append_ledger_event(
                project="demo",
                task_id=task_id,
                run_id=other_run_id,
                trigger_id=None,
                parent_event_id=None,
                event_family="execution",
                event_type="run.started",
                actor_type="system",
                actor_id=None,
                source_type=None,
                source_ref=None,
                status_from=None,
                status_to=None,
                run_status_from=None,
                run_status_to=None,
                severity="info",
                summary="cross project run",
                evidence=None,
                next_action=None,
                context=None,
                idempotency_key="cross-project-run-event",
            )

        with self.assertRaisesRegex(ValueError, "Trigger .* does not belong to project"):
            self.store.append_ledger_event(
                project="demo",
                task_id=task_id,
                run_id=None,
                trigger_id=other_trigger_id,
                parent_event_id=None,
                event_family="dispatch",
                event_type="task.claimed",
                actor_type="system",
                actor_id=None,
                source_type=None,
                source_ref=None,
                status_from=None,
                status_to=None,
                run_status_from=None,
                run_status_to=None,
                severity="info",
                summary="cross project trigger",
                evidence=None,
                next_action=None,
                context=None,
                idempotency_key="cross-project-trigger-event",
            )

        seed_event_id = self.store.append_ledger_event(
            project="demo",
            task_id=task_id,
            run_id=run_id,
            trigger_id=None,
            parent_event_id=None,
            event_family="execution",
            event_type="run.started",
            actor_type="agent",
            actor_id="codex-c",
            source_type="manual",
            source_ref="cli:test",
            status_from="ready",
            status_to="in_progress",
            run_status_from="running",
            run_status_to="running",
            severity="info",
            summary="reference seed event",
            evidence=None,
            next_action=None,
            context=None,
            idempotency_key="reference-seed-event",
        )

        with self.assertRaisesRegex(ValueError, "Parent event .* does not belong to project"):
            self.store.append_ledger_event(
                project="other",
                task_id=other_task_id,
                run_id=other_run_id,
                trigger_id=None,
                parent_event_id=seed_event_id,
                event_family="feedback",
                event_type="handoff.recorded",
                actor_type="human",
                actor_id="reviewer",
                source_type="manual",
                source_ref="cli:other",
                status_from="ready",
                status_to="ready",
                run_status_from="running",
                run_status_to="running",
                severity="info",
                summary="parent mismatch",
                evidence=None,
                next_action=None,
                context=None,
                idempotency_key="parent-mismatch-event",
            )

    def test_ledger_event_queries_order_by_occurred_at(self) -> None:
        self.store.create_project("demo", "example/demo")
        task_id = self.store.add_task(
            project="demo",
            title="ordering-test",
            description=None,
            priority=3,
            impact=3,
            effort=3,
            source="manual",
            external_id=None,
        )
        run_id = self.store.create_run(
            task_id=task_id,
            project="demo",
            trigger_type="manual",
            trigger_ref="cli:test",
            adapter="mock",
            agent_name="codex-e",
            idempotency_key="ordering-test-run",
        )

        first_event_id = self.store.append_ledger_event(
            project="demo",
            task_id=task_id,
            run_id=run_id,
            trigger_id=None,
            parent_event_id=None,
            event_family="feedback",
            event_type="progress.reported",
            actor_type="agent",
            actor_id="codex-e",
            source_type="manual",
            source_ref="cli:test",
            status_from="ready",
            status_to="in_progress",
            run_status_from="running",
            run_status_to="running",
            severity="info",
            summary="later event inserted first",
            evidence=None,
            next_action=None,
            context=None,
            idempotency_key="ordering-test-1",
            occurred_at="2026-04-02 12:00:00",
        )
        second_event_id = self.store.append_ledger_event(
            project="demo",
            task_id=task_id,
            run_id=run_id,
            trigger_id=None,
            parent_event_id=first_event_id,
            event_family="feedback",
            event_type="handoff.recorded",
            actor_type="human",
            actor_id="reviewer",
            source_type="manual",
            source_ref="cli:test",
            status_from="in_progress",
            status_to="in_progress",
            run_status_from="running",
            run_status_to="running",
            severity="info",
            summary="earlier event inserted second",
            evidence=None,
            next_action=None,
            context=None,
            idempotency_key="ordering-test-2",
            occurred_at="2026-04-02 09:00:00",
        )

        task_rows = self.store.list_task_timeline(task_id, limit=10)
        audit_rows = self.store.list_project_audit_events("demo", limit=10)
        project_rows = self.store.list_project_events("demo", after_id=0, limit=10)
        project_rows_after_first = self.store.list_project_events("demo", after_id=first_event_id, limit=10)

        self.assertEqual(first_event_id, int(task_rows[0]["id"]))
        self.assertEqual("progress.reported", task_rows[0]["event_type"])
        self.assertEqual(second_event_id, int(task_rows[1]["id"]))
        self.assertEqual(first_event_id, int(audit_rows[0]["id"]))
        self.assertEqual(second_event_id, int(audit_rows[1]["id"]))
        self.assertEqual(first_event_id, int(project_rows[0]["id"]))
        self.assertEqual(second_event_id, int(project_rows[1]["id"]))
        self.assertEqual(1, len(project_rows_after_first))
        self.assertEqual(second_event_id, int(project_rows_after_first[0]["id"]))

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


if __name__ == "__main__":
    unittest.main()
