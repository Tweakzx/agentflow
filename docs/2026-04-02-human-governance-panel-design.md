# AgentFlow Human Governance Panel Design

Date: 2026-04-02

## 1. Product Positioning

AgentFlow is an agent control plane.

- Agent is the primary executor.
- Human is the governance operator.
- UI should optimize for intervention, not low-level execution input.

## 2. UX Principle

1. Human chooses governance actions.
2. System chooses execution route.
3. Every intervention is auditable.

## 3. Information Architecture

## 3.1 Overview (Home)

Purpose: Health + risk at a glance.

Cards:
- throughput today (`running`, `passed`, `blocked`)
- risk metrics (`gate_fail_rate`, `duplicate_run_rate`, `reclaim_count`)
- queue health (`queue_depth`, `stale_in_progress_count`)
- exception backlog (`manual_attention_count`)

Top actions:
- pause queue
- resume queue
- open exception center

## 3.2 Stage Board

Columns:
- `todo`, `ready`, `in_progress`, `review`, `done`, `blocked`

Card fields:
- title
- priority/impact/effort score
- assigned owner (if any)
- latest run state
- latest error code (if blocked)

Allowed manual actions:
- takeover
- reassign
- force move (requires reason)

## 3.3 Exception Center (Primary Human Workspace)

Purpose: Human intervention workflow.

Grouping:
- by `error_code`
- by project
- by age/severity

Per-group actions:
- retry now
- route to human
- switch policy (`strict`/`fast`/`solo`)

Detail pane:
- latest 3 failed runs
- gate output summary
- suggested action template

## 3.4 Task Detail

Sections:
- task context (source, labels, repo)
- run timeline (claim/edit/gate/finalize)
- audit chain (trigger -> run -> transition)
- intervention log

Governance controls:
- retry
- reassign
- force move
- add operator note

## 3.5 Policy & Routing

Project-level settings:
- default adapter
- agent pool
- routing rules (by source/label/type)
- policy profile (`strict`, `fast`, `solo`)

Important: no per-run adapter/agent mandatory input in main flow.

## 4. Agent Surface (for agent integrations)

Core API capability categories:
- claim next task
- start run (auto-routed)
- progress heartbeat/update
- finalize run
- allowed state transition

Agent should receive:
- task context
- policy snapshot
- gate requirements
- `run_id` / `trace_id` / idempotency key

Agent should not decide:
- final adapter selection in default path
- manual force move without policy permission

## 5. Backend API Changes

## 5.1 Run API

Current behavior:
- `/api/task/<id>/run` accepts explicit `adapter` and `agent` as normal path.

Target behavior:
- make `adapter` and `agent` optional
- add automatic route resolution
- keep override fields only for advanced mode

Request (target):
```json
{
  "project": "demo",
  "mode": "auto",
  "override": {
    "adapter": "openclaw",
    "agent": "openclaw-agent"
  }
}
```

Response (target):
```json
{
  "ok": true,
  "run_id": 123,
  "route": {
    "adapter": "openclaw",
    "agent": "openclaw-agent",
    "reason": "rule:source=github->openclaw/default-agent-pool"
  }
}
```

## 5.2 New Policy API

- `GET /api/policy?project=<project>`
- `PUT /api/policy?project=<project>`
- `GET /api/routing/preview?project=<project>&task_id=<id>`

## 5.3 Exception API

- `GET /api/exceptions?project=<project>&group_by=error_code`
- `POST /api/task/<id>/retry`
- `POST /api/task/<id>/takeover`
- `POST /api/task/<id>/reassign`

## 5.4 Audit Additions

For all interventions, add evidence fields:
- `action`
- `operator_id`
- `reason`
- `route_before`
- `route_after`

## 6. Data Model Additions

Recommended tables/fields:
- `routing_policies` (project-level)
- `agent_pools`
- `run.route_reason` (text/json)
- `ledger_events.context.route`

## 7. Two-PR Implementation Plan

## PR-1 (Core behavior)

Goal: remove adapter/agent friction in primary path.

Changes:
- backend auto-route resolver
- run endpoint accepts `mode=auto` default
- store route reason in run/ledger
- keep manual override for advanced mode only

Acceptance:
- user can run task without entering adapter/agent
- run is auditable with deterministic route reason

## PR-2 (Human governance UX)

Goal: intervention-first UI.

Changes:
- exception center page
- lightweight policy page
- stage board actions: takeover/reassign/force move with reason

Acceptance:
- operators can resolve blocked tasks from exception center
- all interventions appear in audit trail

## 8. Non-Goals (Current Cycle)

- full multi-tenant RBAC redesign
- replacing current adapter protocol
- deep visual redesign unrelated to governance workflows

