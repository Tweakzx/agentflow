from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from agentflow.services.gates import GateEvaluator
from agentflow.store import Store


class GateTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        db = Path(self.tempdir.name) / "test.db"
        self.store = Store(str(db))
        self.store.create_project("demo", "example/demo")

    def tearDown(self) -> None:
        self.tempdir.cleanup()

    def test_gate_profile_persistence(self) -> None:
        self.store.upsert_gate_profile(
            project="demo",
            required_checks=["unit", "lint"],
            commands=["python3 -c \"print('ok')\""],
            timeout_sec=120,
            retry_policy={"max_retries": 1},
            artifact_policy={"save_logs": True},
        )

        profile = self.store.get_gate_profile("demo")
        self.assertIsNotNone(profile)
        assert profile is not None
        self.assertEqual(["unit", "lint"], profile["required_checks"])
        self.assertEqual(120, profile["timeout_sec"])

    def test_gate_evaluator_success_and_failure(self) -> None:
        evaluator = GateEvaluator(timeout_sec=10)

        success = evaluator.evaluate(["python3 -c \"print('ok')\""])
        self.assertTrue(success.passed)

        failure = evaluator.evaluate(["python3 -c \"import sys; sys.exit(2)\""])
        self.assertFalse(failure.passed)


if __name__ == "__main__":
    unittest.main()
