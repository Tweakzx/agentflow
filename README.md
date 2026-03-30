# AgentFlow

A DB-first task and issue management system designed for multiple coding agents.

## Why

`oss-change-records` works well as notes, but product-style management needs stronger querying, metrics, and automation. This project uses SQLite as source of truth and keeps Markdown export for portability.

## Features (MVP)

- SQLite storage (`projects`, `tasks`, `status_history`, `links`)
- Task lifecycle management with explicit statuses
- Priority scoring + `next` recommendation
- Board and stats views in terminal
- Markdown export per project
- Lightweight HTML dashboard generation
- Multi-agent safe claiming with lease/heartbeat/release
- Adapter protocol for integrating multiple coding agents

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
agentflow board --project kthena
agentflow dashboard --db ./data/agentflow.db --out ./dashboard.html
```

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
