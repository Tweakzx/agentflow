---
name: agentflow
version: 0.1.0
description: Use AgentFlow CLI as a task control-plane from Codex bundle environments.
---

# AgentFlow Skill (Codex Bundle)

## Quick Commands

```bash
agentflow --db ./data/agentflow.db board --project <project>
agentflow --db ./data/agentflow.db run-once --project <project> --adapter openclaw --agent codex-agent
agentflow --db ./data/agentflow.db runs --task-id <task_id>
agentflow --db ./data/agentflow.db run-steps <run_id>
agentflow --db ./data/agentflow.db task-detail --task-id <task_id>
agentflow --db ./data/agentflow.db audit --project <project> --limit 30
```

## Event Inputs

```bash
agentflow --db ./data/agentflow.db discover-issues --project <project> --from-file ./issues.json
agentflow --db ./data/agentflow.db handle-comment --project <project> --payload-file ./comment.json --adapter openclaw --agent codex-webhook
```

## Sub-Agent Progress Tracking

When a sub-agent is running, keep lease alive and append progress:

```bash
curl -X POST "http://127.0.0.1:8787/api/task/<task_id>/progress" \
  -H "Content-Type: application/json" \
  -d '{"agent":"codex-agent","step":"running-tests","detail":"15/23 passing","status":"in_progress"}'
```
