---
name: agentflow
version: 0.1.0
description: Use AgentFlow CLI as a task control-plane from Codex bundle environments.
---

# AgentFlow Skill (Codex Bundle)

## Quick Commands

```bash
agentflow --db ./data/agentflow.db board --project <project>
agentflow --db ./data/agentflow.db run-once --project <project> --adapter mock --agent codex-agent
agentflow --db ./data/agentflow.db runs --task-id <task_id>
agentflow --db ./data/agentflow.db run-steps <run_id>
```

## Event Inputs

```bash
agentflow --db ./data/agentflow.db discover-issues --project <project> --from-file ./issues.json
agentflow --db ./data/agentflow.db handle-comment --project <project> --payload-file ./comment.json --adapter mock --agent codex-webhook
```
