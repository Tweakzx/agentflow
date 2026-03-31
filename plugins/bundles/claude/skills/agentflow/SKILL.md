---
name: agentflow
description: AgentFlow task control-plane operations for Claude-compatible plugin bundles.
---

Use AgentFlow CLI to execute and inspect tasks:

```bash
agentflow --db ./data/agentflow.db board --project <project>
agentflow --db ./data/agentflow.db run-once --project <project> --adapter openclaw --agent claude-agent
agentflow --db ./data/agentflow.db triggers --project <project>
agentflow --db ./data/agentflow.db task-detail --task-id <task_id>
agentflow --db ./data/agentflow.db audit --project <project> --limit 30
```

Progress heartbeat (optional):

```bash
curl -X POST "http://127.0.0.1:8787/api/task/<task_id>/progress" \
  -H "Content-Type: application/json" \
  -d '{"agent":"claude-agent","step":"editing","detail":"patch applied","status":"in_progress"}'
```
