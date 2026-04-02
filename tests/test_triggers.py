from __future__ import annotations

import tempfile
import threading
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

    def test_idempotent_trigger_registration_is_atomic_under_concurrency(self) -> None:
        results: list[dict[str, object]] = []
        errors: list[BaseException] = []
        lock = threading.Lock()
        barrier = threading.Barrier(3)

        def worker() -> None:
            try:
                barrier.wait(timeout=2)
                result = self.service.register_trigger(
                    project="demo",
                    trigger_type="comment",
                    trigger_ref="pr#1:comment#2",
                    idempotency_key="k-atomic",
                    payload="{}",
                )
            except BaseException as exc:  # pragma: no cover - captured for assertion
                with lock:
                    errors.append(exc)
            else:
                with lock:
                    results.append(result)

        threads = [threading.Thread(target=worker) for _ in range(2)]
        for thread in threads:
            thread.start()
        barrier.wait(timeout=2)
        for thread in threads:
            thread.join(timeout=5)

        self.assertEqual([], errors)
        self.assertEqual(2, len(results))
        self.assertEqual({False, True}, {bool(result["duplicate"]) for result in results})
        self.assertEqual(1, len({int(result["trigger_id"]) for result in results}))
        self.assertEqual(1, len(self.store.list_triggers("demo")))


if __name__ == "__main__":
    unittest.main()
