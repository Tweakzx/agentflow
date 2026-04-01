from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from agentflow.adapters.base import AdapterContext
from agentflow.adapters.openclaw import OpenClawAdapter
from agentflow.adapters.registry import AdapterRegistry
from agentflow.store import Store


class _FakeHttpResponse:
    def __init__(self, payload: dict) -> None:
        self._payload = payload

    def read(self) -> bytes:
        return json.dumps(self._payload).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


class OpenClawAdapterTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.db = Path(self.tempdir.name) / "test.db"
        self.store = Store(str(self.db))
        self.store.create_project("demo", "example/demo")
        task_id = self.store.add_task(
            project="demo",
            title="Fix webhook dedupe logic",
            description="duplicate comment should not re-run",
            priority=5,
            impact=4,
            effort=2,
            source="github",
            external_id="104",
        )
        self.task = self.store.get_task(task_id)
        self.context = AdapterContext(
            task=self.task,
            project="demo",
            repo_full_name="example/demo",
            previous_runs=[],
            gate_profile=None,
        )

    def tearDown(self) -> None:
        self.tempdir.cleanup()

    def test_registry_registers_openclaw_adapter(self) -> None:
        registry = AdapterRegistry()
        self.assertIn("openclaw", registry.names())

    def test_execute_success_maps_to_review(self) -> None:
        adapter = OpenClawAdapter(gateway_url="http://gateway.local")
        with patch(
            "agentflow.adapters.openclaw.urllib.request.urlopen",
            return_value=_FakeHttpResponse({"status": "completed", "summary": "done"}),
        ):
            result = adapter.execute(self.context, "codex-worker")
        self.assertTrue(result.success)
        self.assertEqual("review", result.to_status)
        self.assertIn("done", result.note)

    def test_execute_with_pr_url_maps_to_review(self) -> None:
        adapter = OpenClawAdapter(gateway_url="http://gateway.local")
        with patch(
            "agentflow.adapters.openclaw.urllib.request.urlopen",
            return_value=_FakeHttpResponse({"status": "completed", "summary": "opened", "pr_url": "https://x/pr/1"}),
        ):
            result = adapter.execute(self.context, "codex-worker")
        self.assertTrue(result.success)
        self.assertEqual("review", result.to_status)
        self.assertIn("https://x/pr/1", result.note)

    def test_execute_failure_maps_to_blocked(self) -> None:
        adapter = OpenClawAdapter(gateway_url="http://gateway.local")
        with patch(
            "agentflow.adapters.openclaw.urllib.request.urlopen",
            return_value=_FakeHttpResponse({"status": "failed", "summary": "lint failed"}),
        ):
            result = adapter.execute(self.context, "codex-worker")
        self.assertFalse(result.success)
        self.assertEqual("blocked", result.to_status)
        self.assertIn("lint failed", result.note)

    def test_prompt_contains_description_and_repo_context(self) -> None:
        adapter = OpenClawAdapter(gateway_url="http://gateway.local")
        prompt = adapter._build_prompt(self.context)
        self.assertIn("Description:", prompt)
        self.assertIn("duplicate comment should not re-run", prompt)
        self.assertIn("Repository: example/demo", prompt)


if __name__ == "__main__":
    unittest.main()
