from __future__ import annotations

import os
import subprocess
import tempfile
import unittest
from pathlib import Path

from agentflow.store import Store


class CliSmokeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.db = Path(self.tempdir.name) / "test.db"
        self.store = Store(str(self.db))
        self.store.create_project("demo", "example/demo")
        self.task_id = self.store.add_task(
            project="demo",
            title="cli-smoke",
            description=None,
            priority=5,
            impact=4,
            effort=2,
            source="github",
            external_id="42",
        )
        self.run_id = self.store.create_run(
            task_id=self.task_id,
            project="demo",
            trigger_type="comment",
            trigger_ref="pr#1:comment#1",
            adapter="mock",
            agent_name="codex-a",
            idempotency_key="k-cli-1",
        )
        self.store.append_run_step(self.run_id, "claim", "passed", "ok")
        self.store.finalize_run(self.run_id, "passed", gate_passed=True, result_summary="ok")
        self.store.upsert_trigger(
            project="demo",
            trigger_type="comment",
            trigger_ref="pr#1:comment#1",
            idempotency_key="k-cli-1",
            payload="{}",
        )
        self.store.upsert_gate_profile(
            project="demo",
            required_checks=["unit"],
            commands=["python3 -c \"print('ok')\""],
            timeout_sec=60,
            retry_policy={"max_retries": 0},
            artifact_policy={},
        )

    def tearDown(self) -> None:
        self.tempdir.cleanup()

    def _run_cli(self, *args: str) -> str:
        cmd = [
            "python3",
            "-m",
            "agentflow.cli",
            "--db",
            str(self.db),
            *args,
        ]
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            env={**os.environ, "PYTHONPATH": "src"},
            cwd="/home/shawn/github/agentflow",
            check=True,
        )
        return proc.stdout

    def test_runs_and_steps_commands(self) -> None:
        runs_out = self._run_cli("runs", "--task-id", str(self.task_id))
        steps_out = self._run_cli("run-steps", str(self.run_id))
        self.assertIn("status=passed", runs_out)
        self.assertIn("step=claim", steps_out)

    def test_triggers_and_gate_profile_commands(self) -> None:
        trig_out = self._run_cli("triggers", "--project", "demo")
        gate_out = self._run_cli("gate-profile", "--project", "demo")
        self.assertIn("k-cli-1", trig_out)
        self.assertIn("required_checks=['unit']", gate_out)


if __name__ == "__main__":
    unittest.main()
