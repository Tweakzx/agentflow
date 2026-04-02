from __future__ import annotations

import tempfile
import threading
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
        task_id = self.store.add_task(
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

        timeline = self.store.list_task_timeline(task_id, limit=20)
        comment_events = [event for event in timeline if event["event_type"] == "comment.received"]
        self.assertGreaterEqual(len(comment_events), 2)
        self.assertFalse(bool(comment_events[-1]["evidence"].get("duplicate", False)))
        self.assertEqual("5001", comment_events[-1]["evidence"].get("comment_id"))
        self.assertTrue(bool(comment_events[0]["evidence"].get("duplicate", False)))
        self.assertEqual("ignored", comment_events[0]["evidence"].get("disposition"))
        self.assertEqual("warning", comment_events[0]["severity"])

    def test_comment_trigger_preserves_original_run_provenance(self) -> None:
        task_id = self.store.add_task(
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
            "comment": {"id": 5001, "body": "/agentflow run", "user": {"login": "octocat"}},
            "issue": {"number": 77, "title": "existing issue"},
        }

        result = self.webhook.handle_pr_comment(
            project="demo",
            payload=payload,
            adapter="mock",
            agent_name="codex-a",
        )

        self.assertTrue(result.accepted)
        self.assertFalse(result.duplicate)
        self.assertTrue(bool(result.run_success))

        runs = self.store.list_runs(task_id)
        self.assertEqual(1, len(runs))
        self.assertEqual("comment", runs[0]["trigger_type"])
        self.assertEqual("issue#77:comment#5001", runs[0]["trigger_ref"])

        timeline = self.store.list_task_timeline(task_id, limit=20)
        comment_events = [event for event in timeline if event["event_type"] == "comment.received"]
        self.assertEqual(1, len(comment_events))
        comment_trigger_id = comment_events[0]["trigger_id"]

        run_events = [event for event in timeline if event["event_type"] in {"run.started", "step.started", "step.passed", "task.claimed"}]
        self.assertGreaterEqual(len(run_events), 4)
        for event in run_events:
            self.assertEqual("github", event["source_type"])
            self.assertEqual("issue#77:comment#5001", event["source_ref"])
            self.assertEqual(comment_trigger_id, event["trigger_id"])

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

    def test_async_comment_ingestion_records_queued_disposition(self) -> None:
        task_id = self.store.add_task(
            project="demo",
            title="async issue",
            description=None,
            priority=4,
            impact=4,
            effort=2,
            source="github",
            external_id="88",
        )
        payload = {
            "comment": {"id": 5002, "body": "/agentflow run", "user": {"login": "octocat"}},
            "issue": {"number": 88, "title": "async issue"},
        }

        finished = threading.Event()

        result = self.webhook.handle_pr_comment(
            project="demo",
            payload=payload,
            adapter="mock",
            agent_name="codex-a",
            async_run=True,
            on_run_finished=lambda _project, _task_id, _run: finished.set(),
        )

        self.assertTrue(result.accepted)
        self.assertFalse(result.duplicate)
        self.assertIsNone(result.run_success)
        self.assertTrue(finished.wait(timeout=2))

        timeline = self.store.list_task_timeline(task_id, limit=20)
        comment_events = [event for event in timeline if event["event_type"] == "comment.received"]
        self.assertEqual(1, len(comment_events))
        self.assertEqual("queued", comment_events[0]["evidence"].get("disposition"))
        self.assertEqual("octocat", comment_events[0]["actor_id"])
        self.assertEqual("mock", comment_events[0]["context"].get("adapter"))

    def test_async_comment_does_not_queue_or_consume_trigger_when_task_not_claimable(self) -> None:
        task_id = self.store.add_task(
            project="demo",
            title="busy issue",
            description=None,
            priority=4,
            impact=4,
            effort=2,
            source="github",
            external_id="89",
        )
        claimed = self.store.claim_task(task_id, "demo", "other-agent", lease_minutes=15)
        self.assertIsNotNone(claimed)
        payload = {
            "comment": {"id": 5003, "body": "/agentflow run", "user": {"login": "octocat"}},
            "issue": {"number": 89, "title": "busy issue"},
        }

        first = self.webhook.handle_pr_comment(
            project="demo",
            payload=payload,
            adapter="mock",
            agent_name="codex-a",
            async_run=True,
        )

        self.assertTrue(first.accepted)
        self.assertFalse(first.duplicate)
        self.assertFalse(bool(first.run_success))
        self.assertEqual("task not claimable", first.message)
        self.assertIsNone(self.store.get_trigger_by_key("gh:comment:5003"))

        timeline = self.store.list_task_timeline(task_id, limit=20)
        comment_events = [event for event in timeline if event["event_type"] == "comment.received"]
        self.assertEqual(1, len(comment_events))
        self.assertEqual("rejected", comment_events[0]["evidence"].get("disposition"))
        self.assertEqual("warning", comment_events[0]["severity"])

        finished = threading.Event()
        released = self.store.release_claim(task_id, "other-agent", to_status="ready")
        self.assertTrue(released)
        second = self.webhook.handle_pr_comment(
            project="demo",
            payload=payload,
            adapter="mock",
            agent_name="codex-a",
            async_run=True,
            on_run_finished=lambda _project, _task_id, _run: finished.set(),
        )

        self.assertTrue(second.accepted)
        self.assertFalse(second.duplicate)
        self.assertIsNone(second.run_success)
        self.assertTrue(finished.wait(timeout=2))

        timeline = self.store.list_task_timeline(task_id, limit=20)
        comment_events = [event for event in timeline if event["event_type"] == "comment.received"]
        self.assertEqual(2, len(comment_events))
        self.assertEqual("queued", comment_events[0]["evidence"].get("disposition"))

    def test_concurrent_redelivery_after_rejected_async_run_does_not_report_duplicate(self) -> None:
        task_id = self.store.add_task(
            project="demo",
            title="busy issue",
            description=None,
            priority=4,
            impact=4,
            effort=2,
            source="github",
            external_id="90",
        )
        claimed = self.store.claim_task(task_id, "demo", "other-agent", lease_minutes=15)
        self.assertIsNotNone(claimed)
        payload = {
            "comment": {"id": 5004, "body": "/agentflow run", "user": {"login": "octocat"}},
            "issue": {"number": 90, "title": "busy issue"},
        }

        entered = threading.Event()
        proceed = threading.Event()
        original_register = self.webhook.trigger_service.register_trigger
        first_call = True
        patch_lock = threading.Lock()

        def blocking_register_trigger(*args, **kwargs):
            nonlocal first_call
            result = original_register(*args, **kwargs)
            with patch_lock:
                should_block = first_call
                if first_call:
                    first_call = False
            if should_block:
                entered.set()
                self.assertTrue(proceed.wait(timeout=2))
            return result

        self.webhook.trigger_service.register_trigger = blocking_register_trigger  # type: ignore[method-assign]

        results: list[WebhookResult] = []
        errors: list[BaseException] = []
        results_lock = threading.Lock()

        def worker() -> None:
            try:
                result = self.webhook.handle_pr_comment(
                    project="demo",
                    payload=payload,
                    adapter="mock",
                    agent_name="codex-a",
                    async_run=True,
                )
            except BaseException as exc:  # pragma: no cover - assertion helper
                with results_lock:
                    errors.append(exc)
            else:
                with results_lock:
                    results.append(result)

        first_thread = threading.Thread(target=worker)
        second_thread = threading.Thread(target=worker)
        first_thread.start()
        self.assertTrue(entered.wait(timeout=2))
        second_thread.start()
        proceed.set()
        first_thread.join(timeout=5)
        second_thread.join(timeout=5)

        self.assertEqual([], errors)
        self.assertEqual(2, len(results))
        self.assertEqual(["task not claimable", "task not claimable"], sorted(result.message for result in results))
        self.assertEqual([False, False], sorted(bool(result.duplicate) for result in results))

        timeline = self.store.list_task_timeline(task_id, limit=20)
        comment_events = [event for event in timeline if event["event_type"] == "comment.received"]
        self.assertEqual(2, len(comment_events))
        self.assertEqual({"rejected"}, {str(event["evidence"].get("disposition")) for event in comment_events})


if __name__ == "__main__":
    unittest.main()
