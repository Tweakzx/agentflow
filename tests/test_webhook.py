from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from agentflow.adapters.registry import AdapterRegistry
from agentflow.services.runner import Runner
from agentflow.services.webhook import GithubCommentWebhookService
from agentflow.store import Store


class WebhookTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        db = Path(self.tempdir.name) / "test.db"
        self.store = Store(str(db))
        self.store.create_project("demo", "example/demo")
        self.runner = Runner(self.store, AdapterRegistry())
        self.webhook = GithubCommentWebhookService(self.store, self.runner)

    def tearDown(self) -> None:
        self.tempdir.cleanup()

    def test_comment_trigger_runs_once_and_deduplicates(self) -> None:
        self.store.add_task(
            project="demo",
            title="existing issue",
            description=None,
            priority=5,
            impact=4,
            effort=2,
            source="github",
            external_id="77",
        )
        payload = {
            "comment": {"id": 5001, "body": "/agentflow run"},
            "issue": {"number": 77, "title": "existing issue"},
        }

        first = self.webhook.handle_pr_comment(
            project="demo",
            payload=payload,
            adapter="mock",
            agent_name="codex-a",
        )
        second = self.webhook.handle_pr_comment(
            project="demo",
            payload=payload,
            adapter="mock",
            agent_name="codex-a",
        )

        self.assertTrue(first.accepted)
        self.assertFalse(first.duplicate)
        self.assertTrue(bool(first.run_success))

        self.assertTrue(second.accepted)
        self.assertTrue(second.duplicate)

        runs = self.store.list_runs(1)
        self.assertEqual(1, len(runs))

    def test_comment_payload_validation(self) -> None:
        bad_payload = {"comment": "oops", "issue": {"number": 7}}
        out = self.webhook.handle_pr_comment(
            project="demo",
            payload=bad_payload,
            adapter="mock",
            agent_name="codex-a",
        )
        self.assertFalse(out.accepted)
        self.assertIn("malformed payload", out.message)


if __name__ == "__main__":
    unittest.main()
