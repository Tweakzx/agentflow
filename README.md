# AgentFlow

A DB-first task and issue management system designed for multiple coding agents.

## Why

`oss-change-records` works well as notes, but product-style management needs stronger querying, metrics, and automation. This project uses SQLite as source of truth and keeps Markdown export for portability.

## Features (MVP)

- SQLite storage (`projects`, `tasks`, `status_history`, `links`)
- Run ledger (`runs`, `run_steps`, `triggers`, `gate_profiles`)
- Task lifecycle management with explicit statuses
- Priority scoring + `next` recommendation
- Board and stats views in terminal
- Markdown export per project
- Lightweight HTML dashboard generation
- Multi-agent safe claiming with lease/heartbeat/release
- Adapter protocol for integrating multiple coding agents
- Trigger idempotency (`idempotency_key`) to prevent duplicate runs
- Scheduled issue discovery + webhook-style comment execution
- Project gate evaluation and gate-enforced status transitions

## Quick Start

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .

agentflow init --db ./data/agentflow.db
agentflow create-project kthena --repo volcano-sh/kthena
agentflow add-task --project kthena --title "controller partition revision bug" --priority 5 --impact 5 --effort 2 --source github --external-id 841
agentflow next --project kthena
agentflow claim-next --project kthena --agent codex-worker-1
agentflow heartbeat 1 --agent codex-worker-1 --lease-minutes 30
agentflow workers --project kthena
agentflow release 1 --agent codex-worker-1 --to-status approved
agentflow adapters
agentflow run-once --project kthena --adapter mock --agent codex-worker-1
agentflow run-batch --project kthena --adapter mock --agent-prefix worker --count 3
agentflow runs --task-id 1
agentflow run-steps 1
agentflow triggers --project kthena
agentflow gate-profile --project kthena
agentflow discover-issues --project kthena --from-file ./examples/issues.json
agentflow handle-comment --project kthena --payload-file ./examples/comment.json --adapter mock --agent codex-webhook
agentflow board --project kthena
agentflow dashboard --db ./data/agentflow.db --out ./dashboard.html
```

## Implemented Now

- `run-once` / `run-batch` execution orchestration
- Run inspection: `runs`, `run-steps`
- Trigger inspection: `triggers`
- Gate inspection: `gate-profile`
- Scheduled discovery ingestion: `discover-issues`
- Comment-event execution ingestion: `handle-comment`

## Event-Driven Workflow (Current CLI Form)

The current implementation accepts event payload files so you can wire cron/webhooks externally and forward JSON into AgentFlow.

### 1. Scheduled Discovery Payload

`issues.json` example:

```json
[
  { "number": 841, "title": "controller partition revision bug", "priority": 5, "impact": 5, "effort": 2 },
  { "number": 838, "title": "partition percentage support", "priority": 4, "impact": 4, "effort": 3 }
]
```

Ingest:

```bash
agentflow discover-issues --project kthena --from-file ./issues.json
```

### 2. Comment Trigger Payload

`comment.json` example:

```json
{
  "comment": { "id": 5001, "body": "/agentflow run" },
  "issue": { "number": 841, "title": "controller partition revision bug" }
}
```

Handle:

```bash
agentflow handle-comment --project kthena --payload-file ./comment.json --adapter mock --agent codex-webhook
```

## Gate Profiles

Gate profile storage is implemented in `gate_profiles` and enforced by `Runner` when commands are configured for a project.

Current inspection command:

```bash
agentflow gate-profile --project kthena
```

## Testing

Run all tests:

```bash
cd /home/shawn/github/agentflow
PYTHONPATH=src python3 -m unittest discover -s tests -p 'test_*.py' -v
```

## Plugin Packaging

This repository now includes plugin skeletons:

- OpenClaw native plugin: `plugins/openclaw-agentflow/`
- Codex bundle sample: `plugins/bundles/codex/`
- Claude bundle sample: `plugins/bundles/claude/`
- Cursor bundle sample: `plugins/bundles/cursor/`

### OpenClaw Native Plugin (local install)

```bash
openclaw plugins install ./plugins/openclaw-agentflow
openclaw plugins enable agentflow
openclaw gateway restart
```

Then configure under `plugins.entries.agentflow.config`, for example:

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

Exposed by the native plugin:

- Command: `agentflow.run`
- Tool: `agentflow_status`
- HTTP route: `POST /agentflow/webhook/comment`

### Publish to OpenClaw ecosystem

1. Publish `plugins/openclaw-agentflow` as npm package (for example `@tweakzx/openclaw-agentflow`).
2. Ensure package includes `openclaw.plugin.json`, `index.ts`, and README.
3. Submit to OpenClaw Community/Marketplace listing after npm release.

### Bundle compatibility for other agents

Bundle manifests are provided as templates:

- `.codex-plugin/plugin.json`
- `.claude-plugin/plugin.json`
- `.cursor-plugin/plugin.json`

You can package each folder independently if you want dedicated distribution channels for different agent ecosystems.

## Multi-Agent Integration

This repository provides the core engine and CLI. Thin adapters map high-level commands for OpenClaw, Codex, Claude Code, or other coding agents:

- `pm init`
- `pm scan`
- `pm next`
- `pm board`
- `pm sync`
- `pm report`

## Adapter Contract

An adapter implements a normalized interface:

- input: `Task + agent_name`
- output: `AdapterResult(success, note, to_status)`

This keeps AgentFlow focused on queueing and lifecycle management while each adapter handles provider-specific execution.

## Status Values

`pending -> approved -> in_progress -> pr_ready -> pr_open -> merged`

Alternative terminal states: `skipped`, `blocked`.
