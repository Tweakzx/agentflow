from __future__ import annotations

import os
import json
import subprocess
import tempfile
import unittest
from pathlib import Path

from agentflow.cli import _parser
from agentflow.store import Store

REPO_ROOT = Path(__file__).resolve().parents[1]


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
            cwd=str(REPO_ROOT),
            check=True,
        )
        return proc.stdout

    def _run_cli_rc(self, *args: str) -> tuple[int, str, str]:
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
            cwd=str(REPO_ROOT),
            check=False,
        )
        return proc.returncode, proc.stdout, proc.stderr

    def test_runs_and_steps_commands(self) -> None:
        runs_out = self._run_cli("runs", "--task-id", str(self.task_id))
        steps_out = self._run_cli("run-steps", str(self.run_id))
        self.assertIn("status=passed", runs_out)
        self.assertIn("step=claim", steps_out)

    def test_task_detail_audit_and_recent_runs_commands(self) -> None:
        detail_out = self._run_cli("task-detail", "--task-id", str(self.task_id))
        audit_out = self._run_cli("audit", "--project", "demo", "--limit", "5")
        recent_out = self._run_cli("recent-runs", "--project", "demo", "--limit", "5")
        self.assertIn('"task"', detail_out)
        self.assertIn('"history"', detail_out)
        self.assertIn("to=pending", audit_out)
        self.assertIn("task=", recent_out)

    def test_json_output_modes(self) -> None:
        board_out = self._run_cli("board", "--project", "demo", "--json")
        detail_out = self._run_cli("task-detail", "--task-id", str(self.task_id), "--json")
        board_data = json.loads(board_out)
        detail_data = json.loads(detail_out)
        self.assertIsInstance(board_data, list)
        self.assertIn("task", detail_data)

    def test_claim_next_creates_running_run(self) -> None:
        out = self._run_cli("claim-next", "--project", "demo", "--agent", "worker-x")
        self.assertIn("in_progress", out)
        runs = self.store.list_runs(self.task_id)
        self.assertTrue(any(str(r["status"]) == "running" for r in runs))

    def test_triggers_and_gate_profile_commands(self) -> None:
        trig_out = self._run_cli("triggers", "--project", "demo")
        gate_out = self._run_cli("gate-profile", "--project", "demo")
        self.assertIn("k-cli-1", trig_out)
        self.assertIn("required_checks=['unit']", gate_out)

    def test_discovery_and_comment_commands(self) -> None:
        issues_file = Path(self.tempdir.name) / "issues.json"
        issues_file.write_text(
            '[{"number": 555, "title": "new issue from schedule", "priority": 4, "impact": 4, "effort": 2}]',
            encoding="utf-8",
        )
        comment_file = Path(self.tempdir.name) / "comment.json"
        comment_file.write_text(
            '{"comment":{"id":9009,"body":"/agentflow run"},"issue":{"number":555,"title":"new issue from schedule"}}',
            encoding="utf-8",
        )

        disc_out = self._run_cli("discover-issues", "--project", "demo", "--from-file", str(issues_file))
        webhook_out = self._run_cli(
            "handle-comment",
            "--project",
            "demo",
            "--payload-file",
            str(comment_file),
            "--adapter",
            "mock",
            "--agent",
            "codex-webhook",
        )

        self.assertIn("created=1", disc_out)
        self.assertIn("accepted=True", webhook_out)

    def test_serve_command_parser_defaults(self) -> None:
        args = _parser().parse_args(["serve"])
        self.assertEqual(args.command, "serve")
        self.assertEqual(args.host, "127.0.0.1")
        self.assertEqual(args.port, 8787)
        self.assertIsNone(args.github_webhook_secret)

    def test_sync_issues_parser(self) -> None:
        args = _parser().parse_args(["sync-issues", "--project", "demo", "--repo", "owner/repo"])
        self.assertEqual(args.command, "sync-issues")
        self.assertEqual(args.project, "demo")
        self.assertEqual(args.repo, "owner/repo")

    def test_move_invalid_status_returns_friendly_error(self) -> None:
        rc, _out, err = self._run_cli_rc("move", str(self.task_id), "not_a_status")
        self.assertEqual(1, rc)
        self.assertIn("error: Invalid status", err)
        self.assertNotIn("Traceback", err)

    def test_export_md_accepts_project_flag(self) -> None:
        args = _parser().parse_args(["export-md", "--out", self.tempdir.name, "--project", "demo"])
        self.assertEqual(args.command, "export-md")
        self.assertEqual(args.project, "demo")

    def test_export_md_project_outputs_single_board(self) -> None:
        second = Store(str(self.db))
        second.create_project("other", "example/other")
        second.add_task(
            project="other",
            title="other-task",
            description=None,
            priority=3,
            impact=3,
            effort=2,
            source=None,
            external_id=None,
        )
        out_dir = Path(self.tempdir.name) / "exports"
        output = self._run_cli("export-md", "--out", str(out_dir), "--project", "demo")
        self.assertIn("demo-board.md", output)
        self.assertTrue((out_dir / "demo-board.md").exists())
        self.assertFalse((out_dir / "other-board.md").exists())

    def test_export_md_project_rejects_unknown_project(self) -> None:
        out_dir = Path(self.tempdir.name) / "exports-missing"
        output = self._run_cli("export-md", "--out", str(out_dir), "--project", "missing")
        self.assertEqual(output.strip(), "no projects found")
        self.assertFalse((out_dir / "missing-board.md").exists())

    def test_db_flag_supported_before_and_after_subcommand(self) -> None:
        args_before = _parser().parse_args(["--db", "/tmp/a.db", "init"])
        args_after = _parser().parse_args(["init", "--db", "/tmp/b.db"])
        self.assertEqual(args_before.db, "/tmp/a.db")
        self.assertEqual(args_after.db, "/tmp/b.db")

    def test_move_supports_project_flag_and_checks_membership(self) -> None:
        self.store.move_task(self.task_id, "approved", "prepare move test")
        move_ok = self._run_cli("move", str(self.task_id), "in_progress", "--project", "demo")
        self.assertIn("moved to in_progress", move_ok)

        # Move it back for mismatch check.
        self.store.move_task(self.task_id, "approved", "prepare mismatch test")
        cmd = [
            "python3",
            "-m",
            "agentflow.cli",
            "--db",
            str(self.db),
            "move",
            str(self.task_id),
            "in_progress",
            "--project",
            "other",
        ]
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            env={**os.environ, "PYTHONPATH": "src"},
            cwd=str(REPO_ROOT),
            check=False,
        )
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("belongs to project 'demo'", proc.stderr)

    def test_cli_subprocess_uses_dynamic_repo_root_cwd(self) -> None:
        original = subprocess.run
        captured: dict[str, object] = {}

        def fake_run(*args: object, **kwargs: object) -> subprocess.CompletedProcess[str]:
            captured["cwd"] = kwargs.get("cwd")
            return subprocess.CompletedProcess(args=args[0], returncode=0, stdout="", stderr="")

        subprocess.run = fake_run  # type: ignore[assignment]
        try:
            self._run_cli("board", "--project", "demo")
        finally:
            subprocess.run = original  # type: ignore[assignment]

        self.assertEqual(str(REPO_ROOT), captured["cwd"])


if __name__ == "__main__":
    unittest.main()
