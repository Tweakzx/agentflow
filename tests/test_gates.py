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
            commands=[{"command": "python3", "args": ["-c", "print('ok')"]}],
            timeout_sec=120,
            retry_policy={"max_retries": 1},
            artifact_policy={"save_logs": True},
        )

        profile = self.store.get_gate_profile("demo")
        self.assertIsNotNone(profile)
        assert profile is not None
        self.assertEqual(["unit", "lint"], profile["required_checks"])
        self.assertEqual([{"command": "python3", "args": ["-c", "print('ok')"]}], profile["commands"])
        self.assertEqual(120, profile["timeout_sec"])

    def test_gate_evaluator_success_and_failure(self) -> None:
        evaluator = GateEvaluator(timeout_sec=10, strict_allowlist=False)

        success = evaluator.evaluate(["python3 -c \"print('ok')\""])
        self.assertTrue(success.passed)

        failure = evaluator.evaluate(["python3 -c \"import sys; sys.exit(2)\""])
        self.assertFalse(failure.passed)

    def test_gate_evaluator_supports_structured_commands_without_shell(self) -> None:
        evaluator = GateEvaluator(timeout_sec=10, strict_allowlist=False)
        out = evaluator.evaluate(
            [
                {
                    "command": "python3",
                    "args": ["-c", "import sys; print(sys.argv[1])", "a&&b"],
                }
            ]
        )
        self.assertTrue(out.passed)
        self.assertEqual("a&&b", out.checks[0].output)

    def test_gate_allowlist_blocks_unlisted_command_by_default(self) -> None:
        evaluator = GateEvaluator(timeout_sec=10)
        out = evaluator.evaluate(["echo hi"])
        self.assertFalse(out.passed)
        self.assertEqual(126, out.checks[0].exit_code)
        self.assertIn("strict mode", out.checks[0].output)

    def test_gate_allowlist_opt_out_mode_runs_unlisted_command(self) -> None:
        evaluator = GateEvaluator(timeout_sec=10, strict_allowlist=False)
        out = evaluator.evaluate(["echo hi"])
        self.assertTrue(out.passed)
        self.assertEqual("hi", out.checks[0].output)


if __name__ == "__main__":
    unittest.main()
