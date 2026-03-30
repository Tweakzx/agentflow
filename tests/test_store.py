from __future__ import annotations

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

        wrong_release = self.store.release_claim(claimed.id, "other-agent", to_status="approved")
        self.assertFalse(wrong_release)

        release_ok = self.store.release_claim(claimed.id, "codex", to_status="approved")
        self.assertTrue(release_ok)

        tasks = self.store.list_tasks("demo")
        reset_task = [t for t in tasks if t.id == claimed.id][0]
        self.assertEqual("approved", reset_task.status)
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


if __name__ == "__main__":
    unittest.main()
