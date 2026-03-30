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
from agentflow.console import _build_handler
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
        self.assertIsNotNone(out1["run_success"])
        self.assertEqual(status2, 200)
        self.assertTrue(out2["duplicate"])

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


if __name__ == "__main__":
    unittest.main()
