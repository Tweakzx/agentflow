from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from agentflow.console import (
    CONSOLE_CSS,
    CONSOLE_JS,
    EventStreamBroker,
    INDEX_HTML,
    _create_task_from_payload,
    _flow_stage_for_status,
    _latest_running_run_id,
    _record_task_progress,
    _validate_manual_transition,
)
from agentflow.store import Store


class ConsoleFlowTests(unittest.TestCase):
    def test_flow_stage_mapping(self) -> None:
        self.assertEqual('todo', _flow_stage_for_status('todo'))
        self.assertEqual('ready', _flow_stage_for_status('ready'))
        self.assertEqual('in_progress', _flow_stage_for_status('in_progress'))
        self.assertEqual('review', _flow_stage_for_status('review'))
        self.assertEqual('done', _flow_stage_for_status('done'))
        self.assertEqual('dropped', _flow_stage_for_status('dropped'))
        self.assertEqual('blocked', _flow_stage_for_status('blocked'))
        self.assertEqual('other', _flow_stage_for_status('unknown'))

    def test_manual_transition_validation(self) -> None:
        self.assertIsNone(_validate_manual_transition('todo', 'ready'))
        self.assertIsNone(_validate_manual_transition('ready', 'in_progress'))
        self.assertIsNone(_validate_manual_transition('review', 'done'))
        self.assertIsNotNone(_validate_manual_transition('todo', 'done'))
        self.assertIsNotNone(_validate_manual_transition('done', 'ready'))

    def test_latest_running_run_id_lookup(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "test.db"
            store = Store(str(db))
            store.create_project("demo", "example/demo")
            task_id = store.add_task(
                project="demo",
                title="progress task",
                description=None,
                priority=4,
                impact=4,
                effort=2,
                source="github",
                external_id="88",
            )
            self.assertIsNone(_latest_running_run_id(store, task_id))
            run_id = store.create_run(
                task_id=task_id,
                project="demo",
                trigger_type="manual",
                trigger_ref="runner:mock",
                adapter="mock",
                agent_name="worker-a",
                idempotency_key="k-1",
            )
            self.assertEqual(run_id, _latest_running_run_id(store, task_id))
            store.finalize_run(run_id, "passed", gate_passed=True, result_summary="ok")
            self.assertIsNone(_latest_running_run_id(store, task_id))

    def test_record_task_progress_appends_step_and_heartbeat(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "test.db"
            store = Store(str(db))
            store.create_project("demo", "example/demo")
            task_id = store.add_task(
                project="demo",
                title="progress task",
                description=None,
                priority=4,
                impact=4,
                effort=2,
                source="github",
                external_id="88",
            )
            claimed = store.claim_task(task_id, "demo", "worker-a", lease_minutes=15)
            self.assertIsNotNone(claimed)
            run_id = store.create_run(
                task_id=task_id,
                project="demo",
                trigger_type="manual",
                trigger_ref="runner:mock",
                adapter="mock",
                agent_name="worker-a",
                idempotency_key="k-2",
            )
            out = _record_task_progress(
                store,
                task_id=task_id,
                agent="worker-a",
                step="running-tests",
                detail="15/20 passed",
                status="in_progress",
                lease_minutes=20,
            )
            self.assertEqual(run_id, out["run_id"])
            self.assertTrue(out["heartbeat_ok"])
            steps = store.list_run_steps(run_id)
            self.assertEqual("running-tests", steps[-1]["step_name"])
            self.assertIn("15/20", steps[-1]["log_excerpt"])

    def test_event_stream_broker_backlog(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "test.db"
            store = Store(str(db))
            store.create_project("demo", "example/demo")
            broker = EventStreamBroker(store)
            first_event_id = store.append_ledger_event(
                project="demo",
                task_id=None,
                run_id=None,
                trigger_id=None,
                parent_event_id=None,
                event_family="feedback",
                event_type="progress.reported",
                actor_type="agent",
                actor_id="worker-a",
                source_type="manual",
                source_ref="test:first",
                status_from=None,
                status_to=None,
                run_status_from=None,
                run_status_to=None,
                severity="info",
                summary="worker-a reported progress",
                evidence={"step": "tests"},
                next_action=None,
                context={},
                idempotency_key="console-flow-first",
            )
            second_event_id = store.append_ledger_event(
                project="demo",
                task_id=None,
                run_id=None,
                trigger_id=None,
                parent_event_id=None,
                event_family="feedback",
                event_type="comment.received",
                actor_type="user",
                actor_id="reviewer",
                source_type="github",
                source_ref="issue#1:comment#2",
                status_from=None,
                status_to=None,
                run_status_from=None,
                run_status_to=None,
                severity="info",
                summary="reviewer left feedback",
                evidence={"task_id": 1},
                next_action=None,
                context={},
                idempotency_key="console-flow-second",
            )
            first = broker.publish("demo", store.list_project_events("demo", after_id=max(0, first_event_id - 1), limit=1)[0])
            second = broker.publish("demo", store.list_project_events("demo", after_id=max(0, second_event_id - 1), limit=1)[0])
            self.assertLess(first, second)
            events = broker.since("demo", first)
            self.assertEqual(1, len(events))
            self.assertEqual("feedback", events[0]["event_family"])
            self.assertEqual("comment.received", events[0]["event_type"])
            self.assertEqual({"task_id": 1}, events[0]["evidence"])
            self.assertNotIn("payload", events[0])

    def test_event_stream_broker_wait_for_returns_all_store_events_after_last_seen(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "test.db"
            store = Store(str(db))
            store.create_project("demo", "example/demo")
            broker = EventStreamBroker(store)
            first_id = store.append_ledger_event(
                project="demo",
                task_id=None,
                run_id=None,
                trigger_id=None,
                parent_event_id=None,
                event_family="execution",
                event_type="run.started",
                actor_type="agent",
                actor_id="worker-a",
                source_type="manual",
                source_ref="test:first",
                status_from=None,
                status_to=None,
                run_status_from=None,
                run_status_to="running",
                severity="info",
                summary="run started",
                evidence={},
                next_action=None,
                context={},
                idempotency_key="console-flow-live-1",
            )
            second_id = store.append_ledger_event(
                project="demo",
                task_id=None,
                run_id=None,
                trigger_id=None,
                parent_event_id=None,
                event_family="execution",
                event_type="step.started",
                actor_type="agent",
                actor_id="worker-a",
                source_type="manual",
                source_ref="test:second",
                status_from=None,
                status_to=None,
                run_status_from="running",
                run_status_to="running",
                severity="info",
                summary="step started",
                evidence={},
                next_action=None,
                context={},
                idempotency_key="console-flow-live-2",
            )
            third_event_id = store.append_ledger_event(
                project="demo",
                task_id=None,
                run_id=None,
                trigger_id=None,
                parent_event_id=None,
                event_family="execution",
                event_type="run.finished",
                actor_type="agent",
                actor_id="worker-a",
                source_type="manual",
                source_ref="test:third",
                status_from=None,
                status_to=None,
                run_status_from="running",
                run_status_to="passed",
                severity="info",
                summary="run finished",
                evidence={},
                next_action=None,
                context={},
                idempotency_key="console-flow-live-3",
            )
            self.assertLess(first_id, second_id)
            self.assertLess(second_id, third_event_id)

            broker.publish("demo", store.list_project_events("demo", after_id=max(0, third_event_id - 1), limit=1)[0])
            events = broker.wait_for("demo", first_id, timeout_sec=0.5)

            self.assertEqual(
                ["step.started", "run.finished"],
                [str(event["event_type"]) for event in events],
            )

    def test_create_task_from_payload(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "test.db"
            store = Store(str(db))
            store.create_project("demo", "example/demo")
            out = _create_task_from_payload(
                store,
                {
                    "project": "demo",
                    "title": "create via api",
                    "description": "desc",
                    "priority": 4,
                    "impact": 5,
                    "effort": 2,
                    "source": "github",
                    "external_id": "900",
                },
            )
            self.assertTrue(out["ok"])
            task = store.get_task(int(out["task_id"]))
            self.assertIsNotNone(task)
            assert task is not None
            self.assertEqual("create via api", task.title)

    def test_console_boot_error_ui_has_retry(self) -> None:
        self.assertIn("Console load failed", CONSOLE_JS)
        self.assertIn("window.location.reload()", CONSOLE_JS)

    def test_refresh_all_reloads_projects_when_none_selected(self) -> None:
        self.assertIn("if (!currentProject()) {\n        await loadProjects();", CONSOLE_JS)

    def test_task_list_uses_collapsible_status_groups(self) -> None:
        self.assertIn('status-accordion', CONSOLE_JS)
        self.assertIn('class="status-group"', CONSOLE_JS)

    def test_console_audit_renderer_uses_ledger_fields(self) -> None:
        self.assertIn("e.event_type", CONSOLE_JS)
        self.assertIn("e.status_from", CONSOLE_JS)
        self.assertIn("e.occurred_at || e.recorded_at", CONSOLE_JS)
        self.assertIn("e.summary", CONSOLE_JS)

    def test_console_does_not_include_custom_favicon(self) -> None:
        self.assertIn('rel="icon"', INDEX_HTML)
        self.assertIn("data:image/svg+xml", INDEX_HTML)
        self.assertIn("%F0%9F%A6%8A", INDEX_HTML)

    def test_console_does_not_render_stage_board(self) -> None:
        self.assertNotIn("Stage Board", INDEX_HTML)
        self.assertIn("Task List", INDEX_HTML)

    def test_console_title_and_brand_include_fox(self) -> None:
        self.assertIn("<title>AgentFlow Console</title>", INDEX_HTML)
        self.assertIn("🦊 AgentFlow Console", INDEX_HTML)

    def test_console_uses_external_template_assets(self) -> None:
        self.assertIn('/static/console.css?v=dev', INDEX_HTML)
        self.assertIn('/static/console.js?v=dev', INDEX_HTML)
        self.assertTrue(CONSOLE_CSS.strip())
        self.assertTrue(CONSOLE_JS.strip())


if __name__ == '__main__':
    unittest.main()
