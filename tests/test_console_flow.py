from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from agentflow.console import (
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
        self.assertEqual('collected', _flow_stage_for_status('pending'))
        self.assertEqual('triaged', _flow_stage_for_status('approved'))
        self.assertEqual('executing', _flow_stage_for_status('in_progress'))
        self.assertEqual('review', _flow_stage_for_status('pr_ready'))
        self.assertEqual('review', _flow_stage_for_status('pr_open'))
        self.assertEqual('done', _flow_stage_for_status('merged'))
        self.assertEqual('done', _flow_stage_for_status('skipped'))
        self.assertEqual('blocked', _flow_stage_for_status('blocked'))
        self.assertEqual('other', _flow_stage_for_status('unknown'))

    def test_manual_transition_validation(self) -> None:
        self.assertIsNone(_validate_manual_transition('pending', 'approved'))
        self.assertIsNone(_validate_manual_transition('approved', 'in_progress'))
        self.assertIsNone(_validate_manual_transition('pr_open', 'merged'))
        self.assertIsNotNone(_validate_manual_transition('pending', 'merged'))
        self.assertIsNotNone(_validate_manual_transition('merged', 'approved'))

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
            first = broker.publish("demo", "task_update", {"task_id": 1})
            second = broker.publish("demo", "progress", {"task_id": 1})
            self.assertLess(first, second)
            events = broker.since("demo", first)
            self.assertEqual(1, len(events))
            self.assertEqual("progress", events[0]["event"])

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
        self.assertIn("Console load failed", INDEX_HTML)
        self.assertIn("window.location.reload()", INDEX_HTML)


if __name__ == '__main__':
    unittest.main()
