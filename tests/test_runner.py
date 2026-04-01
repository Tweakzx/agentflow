from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from agentflow.adapters.registry import AdapterRegistry
from agentflow.services.runner import Runner
from agentflow.store import Store


class RunnerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        db = Path(self.tempdir.name) / "test.db"
        self.store = Store(str(db))
        self.store.create_project("demo", "example/demo")

    def tearDown(self) -> None:
        self.tempdir.cleanup()

    def test_run_once_transitions_task(self) -> None:
        self.store.add_task(
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
        self.assertEqual("review", record.task.status)

    def test_run_once_empty_queue(self) -> None:
        runner = Runner(self.store, AdapterRegistry())
        record = runner.run_once("demo", "mock", "codex-worker")
        self.assertIsNone(record.task)
        self.assertIn("no claimable", record.message)

    def test_run_once_blocks_when_gate_fails(self) -> None:
        self.store.upsert_gate_profile(
            project="demo",
            required_checks=["unit"],
            commands=["python3 -c \"print('ok')\""],
            timeout_sec=30,
            retry_policy={"max_retries": 0},
            artifact_policy={},
        )
        self.store.add_task(
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
        self.assertIn("blocked by gate allowlist", record.message)

    def test_run_once_allows_unlisted_gate_when_strict_allowlist_disabled(self) -> None:
        with patch.dict(os.environ, {"AGENTFLOW_GATE_STRICT_ALLOWLIST": "0"}, clear=False):
            self.store.upsert_gate_profile(
                project="demo",
                required_checks=["unit"],
                commands=[
                    {
                        "command": "python3",
                        "args": ["-c", "import sys; print(sys.argv[1])", "a&&b"],
                    }
                ],
                timeout_sec=30,
                retry_policy={"max_retries": 0},
                artifact_policy={},
            )
            self.store.add_task(
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
            self.assertTrue(record.success)
            self.assertEqual("review", record.task.status)

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


if __name__ == "__main__":
    unittest.main()
