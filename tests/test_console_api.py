from __future__ import annotations

import hashlib
import hmac
import json
import tempfile
import threading
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib import request

from agentflow.adapters.registry import AdapterRegistry
from agentflow.console import _build_handler, _record_task_progress
from agentflow.services.discovery import IssueDiscoveryService
from agentflow.services.runner import Runner
from agentflow.services.webhook import GithubCommentWebhookService
from agentflow.store import Store


class ConsoleApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.db = Path(self.tempdir.name) / "test.db"
        self.store = Store(str(self.db))
        self.store.create_project("demo", "example/demo")
        self.task_id = self.store.add_task(
            project="demo",
            title="webhook task",
            description=None,
            priority=5,
            impact=5,
            effort=2,
            source="github",
            external_id="42",
        )

    def tearDown(self) -> None:
        if hasattr(self, "server"):
            self.server.shutdown()
            self.server.server_close()
            self.thread.join(timeout=2)
        self.tempdir.cleanup()

    def _start_server(self, secret: str | None = None) -> None:
        runner = Runner(self.store, AdapterRegistry())
        discovery = IssueDiscoveryService(self.store)
        webhook = GithubCommentWebhookService(self.store, runner)
        handler = _build_handler(self.store, runner, discovery, webhook, secret)
        try:
            self.server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        except PermissionError as exc:
            raise unittest.SkipTest(f"sandbox blocks local sockets: {exc}") from exc
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base = f"http://127.0.0.1:{self.server.server_port}"

    def _get_json(self, path: str) -> dict:
        with request.urlopen(f"{self.base}{path}") as resp:
            return json.loads(resp.read().decode("utf-8"))

    def _post_json(self, path: str, payload: dict, headers: dict[str, str] | None = None) -> tuple[int, dict]:
        data = json.dumps(payload).encode("utf-8")
        req = request.Request(
            f"{self.base}{path}",
            data=data,
            headers={"Content-Type": "application/json", **(headers or {})},
            method="POST",
        )
        with request.urlopen(req) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8"))

    def test_stats_and_recent_runs_endpoints(self) -> None:
        self._start_server()
        runner = Runner(self.store, AdapterRegistry())
        runner.run_task("demo", self.task_id, "mock", "tester")

        stats = self._get_json("/api/stats?project=demo")
        recent = self._get_json("/api/runs/recent?project=demo&limit=5")

        self.assertEqual(stats["project"], "demo")
        self.assertIn("status_counts", stats)
        self.assertGreaterEqual(stats["recent_run_count"], 1)
        self.assertGreaterEqual(len(recent["runs"]), 1)
        self.assertEqual(recent["runs"][0]["task_id"], self.task_id)

    def test_api_events_streams_ledger_event_objects(self) -> None:
        self._start_server()
        runner = Runner(self.store, AdapterRegistry())
        run_result = runner.run_task("demo", self.task_id, "mock", "tester")
        self.assertTrue(run_result.success)

        req = request.Request(f"{self.base}/api/events?project=demo&last_event_id=0")
        with request.urlopen(req, timeout=5) as resp:
            lines = []
            while True:
                line = resp.readline().decode("utf-8").strip()
                if not line:
                    break
                lines.append(line)
                if len(lines) > 10:
                    break

        data_line = next(line for line in lines if line.startswith("data: "))
        payload = json.loads(data_line.removeprefix("data: "))
        self.assertIn("event_family", payload)
        self.assertIn("event_type", payload)
        self.assertIn("summary", payload)
        self.assertIn("evidence", payload)
        self.assertNotIn("payload", payload)

    def test_comment_webhook_endpoint_is_idempotent(self) -> None:
        self._start_server()
        payload = {
            "comment": {"id": 9001, "body": "/agentflow run"},
            "issue": {"number": 42, "title": "webhook task"},
        }

        status1, out1 = self._post_json("/webhook/github/comment?project=demo&adapter=mock&agent=bot", payload)
        status2, out2 = self._post_json("/webhook/github/comment?project=demo&adapter=mock&agent=bot", payload)

        self.assertEqual(status1, 200)
        self.assertTrue(out1["accepted"])
        self.assertIn("run_success", out1)
        self.assertEqual(status2, 200)
        self.assertTrue(out2["duplicate"])

    def test_progress_endpoint_appends_run_step(self) -> None:
        self._start_server()
        claimed = self.store.claim_task(self.task_id, "demo", "bot-a", lease_minutes=20)
        self.assertIsNotNone(claimed)
        run_id = self.store.create_run(
            task_id=self.task_id,
            project="demo",
            trigger_type="manual",
            trigger_ref="runner:mock",
            adapter="mock",
            agent_name="bot-a",
            idempotency_key="progress-1",
        )

        status, out = self._post_json(
            f"/api/task/{self.task_id}/progress",
            {"agent": "bot-a", "step": "running-tests", "detail": "3/10 passed", "status": "in_progress"},
        )
        self.assertEqual(status, 200)
        self.assertTrue(out["ok"])
        self.assertEqual(run_id, out["run_id"])

        steps = self.store.list_run_steps(run_id)
        self.assertEqual("running-tests", steps[-1]["step_name"])
        self.assertIn("3/10", steps[-1]["log_excerpt"])

        run_timeline = self.store.list_run_timeline(run_id, limit=20)
        progress_events = [event for event in run_timeline if event["event_type"] == "progress.reported"]
        self.assertEqual(1, len(progress_events))
        self.assertEqual("bot-a", progress_events[0]["actor_id"])
        self.assertEqual("running-tests", progress_events[0]["evidence"].get("step"))
        self.assertEqual("3/10 passed", progress_events[0]["evidence"].get("detail"))
        self.assertEqual("in_progress", progress_events[0]["evidence"].get("status"))

    def test_force_move_writes_force_moved_event(self) -> None:
        self._start_server()

        status, out = self._post_json(
            f"/api/task/{self.task_id}/move",
            {"to_status": "done", "note": "override after manual verification", "force": True},
        )
        self.assertEqual(status, 200)
        self.assertTrue(out["ok"])
        self.assertEqual("done", out["task"]["status"])

        timeline = self.store.list_task_timeline(self.task_id, limit=20)
        force_events = [event for event in timeline if event["event_type"] == "task.force_moved"]
        self.assertEqual(1, len(force_events))
        self.assertEqual("todo", force_events[0]["status_from"])
        self.assertEqual("done", force_events[0]["status_to"])
        self.assertEqual("manual", force_events[0]["source_type"])
        self.assertIn("override after manual verification", force_events[0]["summary"])

    def test_audit_endpoint_reads_project_audit_events(self) -> None:
        self._start_server()
        runner = Runner(self.store, AdapterRegistry())
        run_result = runner.run_task("demo", self.task_id, "mock", "tester")
        self.assertTrue(run_result.success)

        data = self._get_json("/api/audit?project=demo&limit=10")

        self.assertEqual("demo", data["project"])
        self.assertGreaterEqual(len(data["events"]), 1)
        self.assertIn("event_family", data["events"][0])
        self.assertIn("event_type", data["events"][0])
        self.assertIn("summary", data["events"][0])
        self.assertNotIn("payload", data["events"][0])

    def test_webhook_signature_required_when_secret_enabled(self) -> None:
        secret = "top-secret"
        self._start_server(secret=secret)
        payload = {
            "comment": {"id": 9101, "body": "/agentflow run"},
            "issue": {"number": 42, "title": "webhook task"},
        }
        body = json.dumps(payload).encode("utf-8")
        signature = "sha256=" + hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()

        req = request.Request(
            f"{self.base}/webhook/github/comment?project=demo&adapter=mock&agent=bot",
            data=body,
            headers={
                "Content-Type": "application/json",
                "X-Hub-Signature-256": signature,
            },
            method="POST",
        )
        with request.urlopen(req) as resp:
            data = json.loads(resp.read().decode("utf-8"))

        self.assertEqual(resp.status, 200)
        self.assertTrue(data["accepted"])

    def test_task_detail_includes_timeline_recent_runs_and_summary(self) -> None:
        self._start_server()
        runner = Runner(self.store, AdapterRegistry())
        run_result = runner.run_task("demo", self.task_id, "mock", "tester")
        self.assertTrue(run_result.success)

        data = self._get_json(f"/api/task/{self.task_id}")

        self.assertIn("task", data)
        self.assertIn("timeline", data)
        self.assertIn("recent_runs", data)
        self.assertIn("derived_summary", data)
        self.assertEqual(self.task_id, data["task"]["id"])
        self.assertGreaterEqual(len(data["timeline"]), 1)
        self.assertGreaterEqual(len(data["recent_runs"]), 1)
        self.assertIsInstance(data["derived_summary"], dict)
        self.assertIn("latest_progress", data["derived_summary"])
        self.assertIn("latest_handoff", data["derived_summary"])
        self.assertIn("latest_risk", data["derived_summary"])
        self.assertIn("recommended_actions", data["derived_summary"])

    def test_progress_helper_and_force_move_use_store_ledger_hooks(self) -> None:
        claimed = self.store.claim_task(self.task_id, "demo", "bot-a", lease_minutes=20)
        self.assertIsNotNone(claimed)
        run_id = self.store.create_run(
            task_id=self.task_id,
            project="demo",
            trigger_type="manual",
            trigger_ref="runner:mock",
            adapter="mock",
            agent_name="bot-a",
            idempotency_key="progress-helper-1",
        )

        out = _record_task_progress(
            self.store,
            task_id=self.task_id,
            agent="bot-a",
            step="running-tests",
            detail="3/10 passed",
            status="in_progress",
            lease_minutes=30,
        )
        self.assertTrue(out["ok"])
        self.assertEqual(run_id, out["run_id"])

        run_timeline = self.store.list_run_timeline(run_id, limit=20)
        progress_events = [event for event in run_timeline if event["event_type"] == "progress.reported"]
        self.assertEqual(1, len(progress_events))
        self.assertEqual("running-tests", progress_events[0]["evidence"].get("step"))
        self.assertEqual("3/10 passed", progress_events[0]["evidence"].get("detail"))

        self.store.move_task(
            self.task_id,
            "done",
            "[manual-web] override after manual verification",
            force=True,
            ledger_event={
                "event_family": "governance",
                "event_type": "task.force_moved",
                "actor_type": "user",
                "actor_id": "web-console",
                "source_type": "manual",
                "source_ref": f"console:task:{self.task_id}:move",
                "severity": "warning",
                "summary": "Manual force move to done: [manual-web] override after manual verification",
                "evidence": {"force": True, "note": "[manual-web] override after manual verification"},
                "context": {"stage": "done"},
            },
        )

        timeline = self.store.list_task_timeline(self.task_id, limit=20)
        force_events = [event for event in timeline if event["event_type"] == "task.force_moved"]
        self.assertEqual(1, len(force_events))
        self.assertEqual("in_progress", force_events[0]["status_from"])
        self.assertEqual("done", force_events[0]["status_to"])


if __name__ == "__main__":
    unittest.main()
