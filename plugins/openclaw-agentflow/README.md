# @tweakzx/openclaw-agentflow

OpenClaw native plugin bridge for AgentFlow.

## Install

```bash
openclaw plugins install ./plugins/openclaw-agentflow
openclaw plugins enable agentflow
openclaw gateway restart
```

## Configure

In OpenClaw config:

```json
{
  "plugins": {
    "entries": {
      "agentflow": {
        "enabled": true,
        "config": {
          "dbPath": "./data/agentflow.db",
          "defaultProject": "kthena",
          "defaultAdapter": "mock",
          "defaultAgentName": "openclaw-agent"
        }
      }
    }
  }
}
```

## Exposed capabilities

- Command: `agentflow.run`
- Tool: `agentflow_status`
- HTTP route: `POST /agentflow/webhook/comment`
