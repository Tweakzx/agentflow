from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

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
        self.assertEqual("pr_ready", record.task.status)

    def test_run_once_empty_queue(self) -> None:
        runner = Runner(self.store, AdapterRegistry())
        record = runner.run_once("demo", "mock", "codex-worker")
        self.assertIsNone(record.task)
        self.assertIn("no claimable", record.message)


if __name__ == "__main__":
    unittest.main()
