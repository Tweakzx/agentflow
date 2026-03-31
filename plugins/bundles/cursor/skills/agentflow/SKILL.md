---
name: agentflow
description: AgentFlow task control-plane operations for Cursor-compatible plugin bundles.
---

Use AgentFlow CLI for task orchestration:

```bash
agentflow --db ./data/agentflow.db next --project <project>
agentflow --db ./data/agentflow.db run-batch --project <project> --adapter openclaw --agent-prefix cursor --count 3
agentflow --db ./data/agentflow.db runs --task-id <task_id>
agentflow --db ./data/agentflow.db task-detail --task-id <task_id>
```

Progress heartbeat (optional):

```bash
curl -X POST "http://127.0.0.1:8787/api/task/<task_id>/progress" \
  -H "Content-Type: application/json" \
  -d '{"agent":"cursor-agent","step":"gate-check","detail":"lint ok, unit running","status":"in_progress"}'
```
