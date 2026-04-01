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
          "defaultProject": "agentflow",
          "defaultAdapter": "openclaw",
          "defaultAgentName": "openclaw-agent"
        }
      }
    }
  }
}
```

## Exposed capabilities

- Command: `agentflow.run`
- Command: `agentflow.create`
- Command: `agentflow.move`
- Command: `agentflow.detail`
- Command: `agentflow.audit`
- Command: `agentflow.help`
- Tool: `agentflow_status`
- Tool: `agentflow_capabilities`
- Tool: `agentflow_create_task`
- Tool: `agentflow_move_task`
- Tool: `agentflow_task_detail`
- Tool: `agentflow_recent_runs`
- Tool: `agentflow_audit`
- HTTP route: `GET /agentflow/capabilities`
- HTTP route: `POST /agentflow/webhook/comment`
- HTTP route: `POST /agentflow/webhook/issues`
- HTTP route: `POST /agentflow/webhook/github`

## Real Adapter Prerequisites

`defaultAdapter` is `openclaw`, which uses AgentFlow's `OpenClawAdapter` under the hood.

Optional environment variables for the adapter process:

- `AGENTFLOW_OPENCLAW_GATEWAY` (default: `http://127.0.0.1:3000`)
- `AGENTFLOW_OPENCLAW_RUNTIME` (default: `acp`)
- `AGENTFLOW_OPENCLAW_TIMEOUT_SEC` (default: `1800`)
- `AGENTFLOW_OPENCLAW_TOKEN` (optional bearer token)
- `AGENTFLOW_ROOT` (optional AgentFlow project root; defaults to plugin-relative `../../`)
- `AGENTFLOW_DEFAULT_PROJECT` (optional fallback project when plugin config omits `defaultProject`)

Tool outputs for detail/runs/audit/board are emitted in JSON mode and returned as structured `data` when parseable.

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
