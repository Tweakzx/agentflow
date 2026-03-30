# AgentFlow Market Analysis and MVP Scope

Date: 2026-03-30

## Problem Statement

Most coding-agent products optimize for single-platform execution. Teams using multiple agents across repositories still need a shared control plane for assignment, lease safety, status normalization, and cross-agent analytics.

## Competitive Snapshot

| Category | Representative Products | Strengths | Gaps for AgentFlow |
|---|---|---|---|
| Platform-native coding agents | GitHub Copilot coding agent, Codex, Cursor background agents | Strong execution UX, built-in IDE/workflow hooks | Usually platform-centric, limited cross-agent lifecycle normalization |
| Ticket-integrated coding agents | Devin + Jira/Linear integrations, OpenHands GitHub action flows | Ticket-to-code automation is mature | Cross-provider scheduling policy and ownership conflict control are weak |
| Multi-agent orchestration frameworks | AutoGen, CrewAI, LangGraph-style orchestration | Flexible orchestration primitives | Need additional product layer for engineering issue lifecycle governance |

## Opportunity Hypothesis

AgentFlow should be a control plane, not another coding model:

1. Normalize task lifecycle across agent providers.
2. Enforce safe parallel work using claim + lease + heartbeat + release.
3. Provide cross-agent throughput and quality analytics.
4. Remain provider-agnostic with adapter interfaces.

## MVP Boundary (4 Weeks)

## Week 1
- Stable DB schema and CLI lifecycle commands.
- Safe parallel claiming and lease control.
- Local dashboard and markdown export.

## Week 2
- Adapter contract + at least one runnable adapter (mock).
- Orchestration commands: run-once, run-batch.
- Error normalization and audit notes.

## Week 3
- Real provider adapter prototype (pick one: OpenClaw/Codex/Claude Code).
- Webhook or polling sync for issue/pr status.
- Basic retry and dead-letter handling.

## Week 4
- Cross-agent metrics: lead time, blocked rate, reclaim frequency.
- Operator playbook and onboarding templates.
- Dogfood on 2 repositories with 15+ issues.

## Go / No-Go Metrics

- >= 20 tasks processed with multi-agent mode.
- Task collision rate < 5%.
- Mean time from claim to first status update < 10 minutes.
- At least 1 real adapter reaches > 70% successful lifecycle closure (to pr_ready/pr_open/merged states, excluding manually blocked items).

## Non-Goals for MVP

- Building a full PM SaaS UI.
- Replacing existing issue trackers.
- Provider-specific advanced optimization before adapter normalization stabilizes.

## Related Docs

- `docs/2026-03-30-control-plane-vs-workflow.md`
