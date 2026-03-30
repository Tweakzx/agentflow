---
name: agentflow
description: AgentFlow task control-plane operations for Claude-compatible plugin bundles.
---

Use AgentFlow CLI to execute and inspect tasks:

```bash
agentflow --db ./data/agentflow.db board --project <project>
agentflow --db ./data/agentflow.db run-once --project <project> --adapter mock --agent claude-agent
agentflow --db ./data/agentflow.db triggers --project <project>
```
