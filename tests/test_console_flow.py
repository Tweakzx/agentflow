from __future__ import annotations

import unittest

from agentflow.console import _flow_stage_for_status


class ConsoleFlowTests(unittest.TestCase):
    def test_flow_stage_mapping(self) -> None:
        self.assertEqual('collected', _flow_stage_for_status('pending'))
        self.assertEqual('triaged', _flow_stage_for_status('approved'))
        self.assertEqual('executing', _flow_stage_for_status('in_progress'))
        self.assertEqual('review', _flow_stage_for_status('pr_ready'))
        self.assertEqual('review', _flow_stage_for_status('pr_open'))
        self.assertEqual('done', _flow_stage_for_status('merged'))
        self.assertEqual('done', _flow_stage_for_status('skipped'))
        self.assertEqual('blocked', _flow_stage_for_status('blocked'))
        self.assertEqual('other', _flow_stage_for_status('unknown'))


if __name__ == '__main__':
    unittest.main()
