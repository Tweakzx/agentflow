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
- Command: `agentflow.help`
- Tool: `agentflow_status`
- Tool: `agentflow_capabilities`
- HTTP route: `GET /agentflow/capabilities`
- HTTP route: `POST /agentflow/webhook/comment`
- HTTP route: `POST /agentflow/webhook/issues`
- HTTP route: `POST /agentflow/webhook/github`

## Agent Discovery Pattern (OpenClaw style)

When an agent is not sure how to use the plugin, it should call:

1. Tool: `agentflow_capabilities` with `{ "mode": "full" }`
2. Command: `agentflow.help` with `{ "mode": "quickstart" }`
3. Optional HTTP: `GET /agentflow/capabilities?mode=quickstart`

This gives the agent:

- plugin defaults (`project/adapter/agent`)
- supported commands/tools/routes
- recommended workflow (discover -> triage -> execute -> observe)

## Typical Agent Workflow

1. Inspect queue: `agentflow_status`
2. Execute next task: `agentflow.run`
3. Event-driven trigger:
   - comments -> `POST /agentflow/webhook/comment`
   - issue discovery -> `POST /agentflow/webhook/issues`
   - generic GitHub webhook -> `POST /agentflow/webhook/github` (`X-GitHub-Event=issues` routes to discovery; others route to comment handler)
4. Re-discover guidance anytime via `agentflow_capabilities`
