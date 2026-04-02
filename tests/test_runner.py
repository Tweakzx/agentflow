from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from agentflow.adapters.registry import AdapterRegistry
from agentflow.services.runner import RunProvenance, Runner
from agentflow.store import Store


class RunnerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        db = Path(self.tempdir.name) / "test.db"
        self.store = Store(str(db))
        self.store.create_project("demo", "example/demo")

    def tearDown(self) -> None:
        self.tempdir.cleanup()

    def _timeline_by_type(self, task_id: int) -> tuple[list[dict[str, object]], dict[str, dict[str, object]]]:
        timeline = self.store.list_task_timeline(task_id)
        return timeline, {str(event["event_type"]): event for event in timeline}

    def test_run_once_transitions_task(self) -> None:
        task_id = self.store.add_task(
            project="demo",
            title="fix crash on startup",
            description=None,
            priority=5,
            impact=5,
            effort=2,
            source="github",
            external_id="101",
        )
        self.store.upsert_gate_profile(
            project="demo",
            required_checks=["unit"],
            commands=['python3 -c "import sys; sys.exit(0)"'],
            timeout_sec=30,
            retry_policy={"max_retries": 0},
            artifact_policy={},
        )
        runner = Runner(self.store, AdapterRegistry())
        record = runner.run_once("demo", "mock", "codex-worker")

        self.assertIsNotNone(record.task)
        assert record.task is not None
        self.assertEqual("review", record.task.status)

        timeline, events = self._timeline_by_type(task_id)
        self.assertEqual(
            [
                "run.finished",
                "task.status_changed",
                "gate.passed",
                "step.passed",
                "step.started",
                "run.started",
                "task.claimed",
            ],
            [event["event_type"] for event in timeline],
        )
        self.assertEqual("passed", events["run.finished"]["run_status_to"])
        self.assertEqual("review", events["task.status_changed"]["status_to"])
        self.assertEqual("gate", events["gate.passed"]["evidence"]["step_name"])
        self.assertEqual("edit", events["step.passed"]["evidence"]["step_name"])

    def test_run_once_empty_queue(self) -> None:
        runner = Runner(self.store, AdapterRegistry())
        record = runner.run_once("demo", "mock", "codex-worker")
        self.assertIsNone(record.task)
        self.assertIn("no claimable", record.message)

    def test_run_once_blocks_when_gate_fails(self) -> None:
        self.store.upsert_gate_profile(
            project="demo",
            required_checks=["unit"],
            commands=["python3 -c \"import sys; sys.exit(3)\""],
            timeout_sec=30,
            retry_policy={"max_retries": 0},
            artifact_policy={},
        )
        task_id = self.store.add_task(
            project="demo",
            title="fix crash on startup",
            description=None,
            priority=5,
            impact=5,
            effort=2,
            source="github",
            external_id="101",
        )
        runner = Runner(self.store, AdapterRegistry())
        record = runner.run_once("demo", "mock", "codex-worker")

        self.assertIsNotNone(record.task)
        assert record.task is not None
        self.assertEqual("blocked", record.task.status)
        self.assertFalse(record.success)

        timeline, events = self._timeline_by_type(task_id)
        self.assertEqual(
            [
                "run.finished",
                "task.status_changed",
                "gate.failed",
                "step.passed",
                "step.started",
                "run.started",
                "task.claimed",
            ],
            [event["event_type"] for event in timeline],
        )
        self.assertEqual("failed", events["run.finished"]["run_status_to"])
        self.assertEqual("blocked", events["task.status_changed"]["status_to"])
        self.assertEqual("gate_failed", events["gate.failed"]["evidence"]["error_code"])

    def test_run_once_execution_failure_preserves_gate_passed_state(self) -> None:
        task_id = self.store.add_task(
            project="demo",
            title="investigate flaky failure",
            description=None,
            priority=5,
            impact=5,
            effort=2,
            source="github",
            external_id="102",
        )
        runner = Runner(self.store, AdapterRegistry())
        record = runner.run_once("demo", "mock", "codex-worker")

        self.assertIsNotNone(record.task)
        assert record.task is not None
        self.assertEqual(task_id, record.task.id)
        self.assertEqual("blocked", record.task.status)
        self.assertFalse(record.success)

        runs = self.store.list_runs(task_id)
        self.assertEqual(1, len(runs))
        self.assertEqual("failed", runs[0]["status"])
        self.assertEqual(1, runs[0]["gate_passed"])
        self.assertEqual("execution_failed", runs[0]["error_code"])

        timeline, events = self._timeline_by_type(task_id)
        self.assertEqual(
            [
                "run.finished",
                "task.status_changed",
                "step.failed",
                "step.started",
                "run.started",
                "task.claimed",
            ],
            [event["event_type"] for event in timeline],
        )
        self.assertNotIn("gate.passed", events)
        self.assertNotIn("gate.failed", events)
        self.assertEqual("failed", events["run.finished"]["run_status_to"])
        self.assertEqual("blocked", events["task.status_changed"]["status_to"])
        self.assertEqual("edit", events["step.failed"]["evidence"]["step_name"])

        run_steps = self.store.list_run_steps(int(runs[0]["id"]))
        self.assertEqual(
            [("claim", "passed"), ("edit", "failed")],
            [(step["step_name"], step["status"]) for step in run_steps],
        )

    def test_run_task_preserves_explicit_provenance(self) -> None:
        task_id = self.store.add_task(
            project="demo",
            title="webhook-triggered task",
            description=None,
            priority=5,
            impact=5,
            effort=2,
            source="github",
            external_id="103",
        )
        trigger_id = self.store.upsert_trigger(
            project="demo",
            trigger_type="comment",
            trigger_ref="issue#77:comment#5001",
            idempotency_key="trigger-provenance-test",
            payload="{}",
        )
        runner = Runner(self.store, AdapterRegistry())
        provenance = RunProvenance(
            trigger_id=trigger_id,
            trigger_type="comment",
            trigger_ref="issue#77:comment#5001",
            source_type="github",
            source_ref="issue#77:comment#5001",
        )

        record = runner.run_task("demo", task_id, "mock", "codex-worker", provenance=provenance)

        self.assertIsNotNone(record.task)
        assert record.task is not None
        self.assertEqual(task_id, record.task.id)

        runs = self.store.list_runs(task_id)
        self.assertEqual(1, len(runs))
        self.assertEqual("comment", runs[0]["trigger_type"])
        self.assertEqual("issue#77:comment#5001", runs[0]["trigger_ref"])

        timeline, events = self._timeline_by_type(task_id)
        self.assertEqual(trigger_id, events["task.claimed"]["trigger_id"])
        self.assertEqual(trigger_id, events["run.started"]["trigger_id"])
        self.assertEqual(trigger_id, events["step.started"]["trigger_id"])
        self.assertEqual(trigger_id, events["step.passed"]["trigger_id"])
        self.assertEqual("github", events["run.started"]["source_type"])
        self.assertEqual("issue#77:comment#5001", events["run.started"]["source_ref"])
        self.assertEqual("github", events["task.claimed"]["source_type"])
        self.assertEqual("issue#77:comment#5001", events["task.claimed"]["source_ref"])
        self.assertEqual("todo", events["task.claimed"]["status_from"])
        self.assertEqual("in_progress", events["task.claimed"]["status_to"])
        self.assertEqual("github", events["task.status_changed"]["source_type"])
        self.assertEqual("issue#77:comment#5001", events["task.status_changed"]["source_ref"])
        self.assertEqual("in_progress", events["task.status_changed"]["status_from"])
        self.assertEqual("review", events["task.status_changed"]["status_to"])
        self.assertEqual("github", events["run.finished"]["source_type"])
        self.assertEqual(trigger_id, events["task.status_changed"]["trigger_id"])
        self.assertEqual(trigger_id, events["run.finished"]["trigger_id"])


if __name__ == "__main__":
    unittest.main()
