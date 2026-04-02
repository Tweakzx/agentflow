from __future__ import annotations

import unittest

from agentflow.services.ledger import build_event, build_gate_failed_event, derive_task_summary


class LedgerServiceTests(unittest.TestCase):
    def test_build_event_normalizes_optional_payloads_and_validates_contract(self) -> None:
        event = build_event(
            event_family="feedback",
            event_type="progress.reported",
            actor_type="human",
            summary="progress noted",
        )

        self.assertEqual("feedback", event["event_family"])
        self.assertEqual("progress.reported", event["event_type"])
        self.assertEqual("human", event["actor_type"])
        self.assertEqual("progress noted", event["summary"])
        self.assertEqual("info", event["severity"])
        self.assertEqual({}, event["evidence"])
        self.assertEqual({}, event["next_action"])
        self.assertEqual({}, event["context"])

        with self.assertRaisesRegex(ValueError, "Unsupported severity"):
            build_event(
                event_family="feedback",
                event_type="progress.reported",
                actor_type="human",
                summary="progress noted",
                severity="critical",
            )

    def test_derive_task_summary_handles_generator_input(self) -> None:
        def events():
            yield {
                "event_type": "progress.reported",
                "summary": "drafting patch",
                "severity": "info",
                "next_action": {"recommended": "continue"},
            }
            yield {
                "event_type": "handoff.recorded",
                "summary": "needs review",
                "severity": "info",
                "next_action": {"recommended": "review"},
            }

        summary = derive_task_summary(events())

        self.assertEqual("progress.reported", summary["latest_progress"]["event_type"])
        self.assertEqual("handoff.recorded", summary["latest_handoff"]["event_type"])
        self.assertEqual(
            [{"id": "review", "label": "Review"}],
            summary["recommended_actions"],
        )

    def test_build_gate_failed_event_payload(self) -> None:
        event = build_gate_failed_event(
            task_id=12,
            run_id=33,
            actor_id="gate-evaluator",
            summary="Gate failed on pytest -q",
            error_code="gate_failed",
            log_excerpt="2 tests failed",
        )

        self.assertEqual("risk", event["event_family"])
        self.assertEqual("gate.failed", event["event_type"])
        self.assertEqual("error", event["severity"])
        self.assertEqual(12, event["task_id"])
        self.assertEqual(33, event["run_id"])
        self.assertEqual(
            {
                "step_name": "gate",
                "error_code": "gate_failed",
                "log_excerpt": "2 tests failed",
            },
            event["evidence"],
        )

    def test_derive_task_summary_prefers_recent_risk_event(self) -> None:
        summary = derive_task_summary(
            [
                {
                    "event_type": "progress.reported",
                    "summary": "editing files",
                    "severity": "info",
                    "next_action": {"recommended": "continue"},
                },
                {
                    "event_type": "gate.failed",
                    "summary": "pytest failed",
                    "severity": "error",
                    "next_action": {
                        "recommended": "takeover",
                        "actions": [{"id": "takeover", "label": "Take Over"}],
                    },
                },
            ]
        )

        self.assertEqual("gate.failed", summary["latest_risk"]["event_type"])
        self.assertEqual("pytest failed", summary["latest_risk"]["summary"])
        self.assertEqual(
            [{"id": "takeover", "label": "Take Over"}],
            summary["recommended_actions"],
        )

    def test_gate_passed_does_not_surface_as_latest_risk(self) -> None:
        summary = derive_task_summary(
            [
                {
                    "event_type": "gate.passed",
                    "summary": "checks passed",
                    "severity": "info",
                    "next_action": {"recommended": "continue"},
                },
                {
                    "event_type": "progress.reported",
                    "summary": "working through tasks",
                    "severity": "info",
                    "next_action": {"recommended": "continue"},
                },
            ]
        )

        self.assertIsNone(summary["latest_risk"])
        self.assertEqual("progress.reported", summary["latest_progress"]["event_type"])


if __name__ == "__main__":
    unittest.main()
