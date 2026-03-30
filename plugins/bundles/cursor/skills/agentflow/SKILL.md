---
name: agentflow
description: AgentFlow task control-plane operations for Cursor-compatible plugin bundles.
---

Use AgentFlow CLI for task orchestration:

```bash
agentflow --db ./data/agentflow.db next --project <project>
agentflow --db ./data/agentflow.db run-batch --project <project> --adapter mock --agent-prefix cursor --count 3
agentflow --db ./data/agentflow.db runs --task-id <task_id>
```
