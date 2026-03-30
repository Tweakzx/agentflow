from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from agentflow.services.triggers import TriggerService
from agentflow.store import Store


class TriggerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        db = Path(self.tempdir.name) / "test.db"
        self.store = Store(str(db))
        self.store.create_project("demo", "example/demo")
        self.service = TriggerService(self.store)

    def tearDown(self) -> None:
        self.tempdir.cleanup()

    def test_idempotent_trigger_registration(self) -> None:
        first = self.service.register_trigger(
            project="demo",
            trigger_type="comment",
            trigger_ref="pr#1:comment#2",
            idempotency_key="k-1",
            payload="{}",
        )
        second = self.service.register_trigger(
            project="demo",
            trigger_type="comment",
            trigger_ref="pr#1:comment#2",
            idempotency_key="k-1",
            payload="{}",
        )

        self.assertFalse(first["duplicate"])
        self.assertTrue(second["duplicate"])
        self.assertEqual(first["trigger_id"], second["trigger_id"])


if __name__ == "__main__":
    unittest.main()
