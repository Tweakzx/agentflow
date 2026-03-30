# 为什么传统 Skill/MCP/Flow 难以“可控”，以及 AgentFlow 的本质差异

日期：2026-03-30

## 背景

在实际使用中，很多团队会发现：
- Skill、MCP、Dify 这类编排方式可以快速把流程“跑起来”；
- 但当任务量变大、Agent 并行增多、跨仓库协作变复杂后，结果越来越不可控；
- 中间过程难记录、难审计、难统一复盘。

这个现象不是偶然，而是系统分层问题。

## 为什么“总是不太行”

## 1. 编排层不等于控制层

Skill/MCP/Flow 更像能力编排层，核心价值是“让 Agent 能调用更多工具做更多事”。

它们通常不提供完整的工程级控制语义：
- 原子认领（claim）
- 租约与续租（lease/heartbeat）
- 超时回收（reclaim）
- 幂等执行（idempotency）
- 严格状态机与转移约束
- 审计账本（谁在何时做了什么）

当这些控制语义缺失时，并行越强，混乱越快。

## 2. LLM 执行天然非确定

同样输入在不同上下文下可能产生不同输出。若仅靠 prompt 约束而没有系统级事务约束，就会出现：
- 状态漂移：任务已做完但状态没更新，或反之
- 重复执行：两个 agent 同时处理同一 issue
- 中途丢失：上下文窗口与会话切换导致历史不可追踪

## 3. “状态真相”分散

传统工作流里，状态经常分散在：
- 对话历史
- 第三方工具评论
- 临时脚本输出
- issue/PR 文本

缺少统一 source of truth，就无法稳定计算吞吐、冲突率、阻塞率和交付周期。

## AgentFlow 与 Skill/MCP/Dify 的本质区别

## 1. 角色分离：控制面 vs 执行器

- AgentFlow：控制面（Control Plane），管理任务生命周期和并发安全。
- 各类 Agent（OpenClaw/Codex/Claude Code/...）：执行器，通过 adapter 接入。

换句话说：
- Skill/MCP/Dify 解决“能做”；
- AgentFlow 解决“做稳、可管、可追责”。

## 2. 状态驱动而非提示词驱动

AgentFlow 以结构化状态机为核心：
`pending -> approved -> in_progress -> pr_ready -> pr_open -> merged`

并提供：
- claim-next
- heartbeat
- release
- workers

这使得并行成为可控操作，而不是“碰运气的并发”。

## 3. 跨 Agent 统一治理

AgentFlow 不绑定单一平台，通过 adapter 标准化输入输出：
- 输入：`Task + agent_name`
- 输出：`AdapterResult(success, note, to_status)`

因此可以在同一治理模型下接入不同 agent 生态。

## 4. 审计与复盘友好

每次状态变更写入 `status_history`，可追踪：
- 谁处理了任务
- 何时处理
- 从哪个状态变到哪个状态
- 变更说明是什么

这对团队复盘和流程优化非常关键。

## 与 Dify/传统工作流的关系

AgentFlow 不是替代 Dify 或 Skill/MCP，而是补上“工程控制层”。

推荐分层：
1. Dify / Skill / MCP：定义执行流程和工具能力。
2. AgentFlow：提供任务队列控制、并发治理、状态账本、统一指标。

二者组合比单独使用任一方更稳。

## 我们可以做得更好的机会点

## 1. 并发治理标准化

把“多 agent 并行”抽象成通用协议：
- claim/lease/heartbeat/release/reclaim
- 冲突检测与重试策略
- 死信队列（dead-letter）

## 2. 跨平台统一指标

统一输出：
- lead time
- blocked rate
- collision rate
- reclaim frequency
- agent-level throughput

从“某个工具跑得怎么样”升级到“整体研发自动化健康度”。

## 3. 运维级可观测性

增加事件流与审计查询能力：
- 事件订阅（task claimed/moved/blocked）
- 规则告警（lease 即将过期、长时间 in_progress）
- 自动催办与人工接管入口

## 4. 适配器生态

围绕统一 adapter 接口扩展：
- OpenClaw adapter
- Codex adapter
- Claude Code adapter
- GitHub-native adapter

形成“控制面统一、执行面可插拔”的产品护城河。

## 结论

如果目标是“单 Agent、少量任务、短周期”，传统 skill/flow 足够。  
如果目标是“多 Agent、长期并行、可审计交付”，必须引入控制面。  
AgentFlow 的价值正是把不可控的智能编排，提升为可治理的工程系统。
