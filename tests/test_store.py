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


if __name__ == "__main__":
    unittest.main()
