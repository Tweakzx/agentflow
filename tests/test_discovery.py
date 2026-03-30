from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from agentflow.services.discovery import IssueDiscoveryService
from agentflow.store import Store


class DiscoveryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        db = Path(self.tempdir.name) / "test.db"
        self.store = Store(str(db))
        self.store.create_project("demo", "example/demo")
        self.discovery = IssueDiscoveryService(self.store)

    def tearDown(self) -> None:
        self.tempdir.cleanup()

    def test_ingest_issues_is_idempotent(self) -> None:
        issues = [
            {"number": 101, "title": "first issue", "priority": 4, "impact": 4, "effort": 2},
            {"number": 102, "title": "second issue", "priority": 3, "impact": 3, "effort": 3},
        ]
        first = self.discovery.ingest_issues("demo", issues)
        second = self.discovery.ingest_issues("demo", issues)

        self.assertEqual(2, first.created)
        self.assertEqual(0, first.skipped)
        self.assertEqual(0, second.created)
        self.assertEqual(2, second.skipped)


if __name__ == "__main__":
    unittest.main()
