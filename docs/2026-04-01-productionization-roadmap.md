# AgentFlow 90 天工作路线图（围绕核心价值重排）

日期：2026-04-01

## 1. 我们的核心价值

在当前代码、README、控制台形态和设计文档里，AgentFlow 的核心价值已经比较清晰，不是“再做一个更强的 agent”，而是做一个让多 Agent 研发执行对人类更可见、更可控、更可接管的控制面。

一句话定义：

> AgentFlow = 面向多 Agent 研发执行的人机协作控制面，让任务推进、执行过程、门禁结果和接管动作都可视化、可治理、可审计。

当前阶段最重要的 4 个价值支点：

1. `治理`
- 用统一状态机、claim / lease / heartbeat / release / reclaim 约束并发执行，减少“agent 很努力但系统不可控”。

2. `可视化`
- 不只展示任务状态，还要展示 run、step、trigger、失败原因、下一步建议，让人类能理解 agent 到底做了什么。

3. `人机协作`
- 人不是旁观者，而是可以批准、接管、重派、强制流转、复盘的操作者。

4. `兼容现有生态`
- AgentFlow 不是替代 OpenClaw/Codex/Claude/Cursor，而是作为上层控制面，统一接入不同 agent 生态。

这意味着接下来 90 天的主线不应是“先扩更多 adapter”，而应是：

> 先把 agent 工作过程结构化呈现给人，再把可靠性和生态扩展建立在这条产品主线上。

## 2. 产品定位与非目标

## 2.1 产品定位

AgentFlow 当前最适合被定义为：

- 一个轻量控制面，而不是完整托管平台
- 一个任务治理与执行可视化层，而不是聊天 UI
- 一个可插拔的 agent 协作枢纽，而不是单一 provider 的深度定制壳

面向用户真正提供的价值是：

- 看见任务正在被谁处理
- 看见 agent 进行到了哪一步
- 看见为什么失败、卡在哪里、下一步怎么办
- 在必要时快速接管，而不是重新建立上下文

## 2.2 明确非目标

本阶段暂不优先追求：

- 自建完整 Agent SaaS 平台
- 先做复杂多租户和商业计费
- 在控制语义未稳定前大规模扩 adapter
- 用“更多自动化”替代“更好的可见性与治理”

## 3. 接下来 90 天的北极星指标

为了让路线图服务核心价值，生产化指标需要同时覆盖可靠性和“对人是否真正可见”。

硬指标：

- 任务冲突率（collision）`< 2%`
- 重复执行率（duplicate run）`< 1%`
- 门禁误放行率（false pass）`= 0`
- webhook 幂等正确率 `= 100%`
- 审计追溯完整率 `= 100%`
- `claim -> 首次进度事件` 的 `P95 < 8 分钟`

新增的人机协作指标：

- 每次自动状态变化都能关联至少 1 条证据记录：`run / step / trigger / note`
- 每个 `blocked` 任务都能在控制台看到失败摘要与最近一步骤上下文
- 每个 `in_progress` 任务都能在控制台看到 owner、lease 和最近活动时间
- 人工接管到恢复自动流程形成闭环，关键动作都有审计事件

## 4. 路线图重排原则

路线图按下面的优先级执行：

1. 先保证 `看得见`
- 没有过程可视化的自动化，只会放大不确定性。

2. 再保证 `做得稳`
- 可重试、可回收、可审计，是控制面成立的基础。

3. 最后才是 `接得广`
- adapter 扩展必须建立在稳定的控制语义和统一事件模型之上。

因此 90 天内的顺序应是：

`事件模型与可视化闭环 -> 可靠性与安全底座 -> 团队策略与生态扩展`

## 5. 90 天路线图

## P0（第 1-3 周）：把 Agent 工作过程真正呈现出来

目标：先把 AgentFlow 从“任务板 + 运行记录”升级为“可解释的执行过程界面”。

### P0-1 统一事件模型

- 将控制台展示对象从“任务状态”扩展到“事件流”
- 明确并固化以下事件类型：
  - `dispatch`
  - `progress`
  - `handoff`
  - `conflict`
  - `recovery`
  - `gate_result`
- 为每类事件定义统一字段：`task_id`、`run_id`、`actor`、`summary`、`evidence`、`next_action`

验收：

- 任务详情页可按时间线展示结构化事件
- 状态变化不再只是 `todo -> in_progress`，而是能看到“谁触发、做了什么、为什么变更”

### P0-2 控制台从 Task-first 升级为 Evidence-first

- 在现有 Stage Board / Task Detail / Recent Runs / Audit 基础上补齐：
  - 最近活动时间
  - 当前 owner 与 lease
  - 最近一次 progress / handoff 摘要
  - gate 失败摘要与关键日志
  - 可恢复动作入口（retry / takeover / reassign）
- 让 `blocked`、`stale in_progress`、`gate failed` 成为一等视图

验收：

- 人类无需看日志文件即可判断任务当前卡点
- `blocked` 任务都能看到失败步骤和简短原因
- `in_progress` 任务都能看到最近活动和是否接近 lease 超时

### P0-3 人工接管闭环

- 增加 `takeover / reassign / force move / resume automation` 的统一动作语义
- 所有人工动作写入审计时间线
- 明确“人工接管后如何恢复自动执行”的状态规则

验收：

- 任一自动执行中的任务都能被控制台接管
- 人工接管后可恢复到自动流程，不丢上下文

### P0-4 证据优先的状态推进规则

- 约束状态推进必须附带上下文证据
- 对缺少证据的自动状态更新降级显示
- 定义最小证据包：
  - 最近 run
  - 最近 step
  - 变更摘要
  - 下一步建议

验收：

- 审计中所有自动状态变化都可回溯到具体 run 或 trigger
- 控制台不再出现“状态变了，但不知道为什么”的记录

## P1（第 4-8 周）：补齐可靠性、安全与可运维底座

目标：让已经可见的控制面在真实项目里持续稳定工作。

### P1-1 队列化执行与失败恢复

- 引入 `queued` 状态与统一 job runner
- webhook 不再直接占用请求线程执行任务
- 增加重试策略（指数退避）
- 增加死信队列（DLQ）
- 增加 lease reclaim 守护任务

验收：

- 失败任务可自动重试并记录 attempt
- 超过阈值进入 DLQ 且控制台可见
- reclaim 周期输出统计并可在 UI 查看

### P1-2 幂等与一致性加固

- 统一入口幂等键规则：`comment / schedule / manual`
- run、trigger、task transition 建立强一致关联
- 增加“同一 task 仅允许一个活跃 running run”的约束

验收：

- webhook 重放不触发重复执行
- 任意一次状态变化都能追溯到 trigger 和 run
- 并发触发下无双 running run

### P1-3 Gate 安全升级

- Gate 从自由字符串升级为结构化命令模板：`command + args`
- 默认启用 allowlist
- 提供策略模板：`strict / fast / solo`
- gate 输出结构化，便于前端摘要呈现

验收：

- 默认策略下非白名单命令不可执行
- gate 失败能展示标准化失败原因与关键输出
- Gate 配置变更可审计

### P1-4 基础可运维性

- 健康检查：`/healthz`、`/readyz`
- 指标：`run_success_rate`、`gate_fail_rate`、`queue_depth`、`reclaim_count`
- 结构化日志（JSON）+ `trace_id`
- 关键动作支持最小排障链路

验收：

- 关键流程可被探针和监控系统接入
- 发生失败时可从 trace_id 回溯 task/run/trigger

## P2（第 9-12 周）：把控制面做成团队能力

目标：在核心价值稳定后，再扩到团队场景、策略层和多生态。

### P2-1 Adapter Contract v1

- 固化 `discover / create / update / sync / run` 契约
- 为事件、状态、错误码、审计字段定义统一规范
- 建立 adapter conformance tests

验收：

- 新 adapter 接入时不需要重新定义控制语义
- 至少 1 个 OpenClaw 之外的主流 adapter 接入并通过 conformance tests

### P2-2 规则与策略层

- 项目级策略：自动准入、风险分级、必需审批人
- 任务路由：按类型/标签分配 agent 或 adapter
- timebox 策略：超时降级、转人工、重新调度

验收：

- 策略可配置、可解释、可审计
- 路由和人工接管规则在 UI 可见

### P2-3 AgentOps 指标产品化

- 指标：lead time、blocked rate、reclaim frequency、collision rate
- 维度：repo / agent / provider
- 周报自动化推送（Slack/飞书）

验收：

- 能按 repo / agent / provider 观察吞吐和风险
- 能输出控制面健康周报

### P2-4 更完整的团队化能力

- RBAC（viewer / operator / admin）
- 项目级隔离、凭据隔离
- SQLite -> Postgres 路径设计
- worker 水平扩展与灰度发布策略

验收：

- 团队环境下具备基本权限与部署演进能力

## 6. 本周行动清单

基于上面的优先级，本周建议不再把工作重心放在“再接一个 adapter”，而是先把“可见性主线”补全。

- 定义 `event model v1`：事件类型、字段、来源、证据结构
- 补控制台任务详情：最近进度、最近 handoff、失败摘要、下一步建议
- 增加 `blocked` / `stale in_progress` / `gate failed` 三个高价值视图
- 设计并落地人工接管动作：`takeover / reassign / resume automation`
- 统一 `run -> step -> audit -> task` 的前端展示映射
- 补 6 个核心 SLO 与人机协作指标的统计口径

## 7. 建议拆分为独立 PR 的执行顺序

- PR-A：路线图与事件模型文档
- PR-B：控制台可视化增强（evidence-first task detail）
- PR-C：人工接管与恢复自动流程
- PR-D：queue / retry / reclaim / DLQ
- PR-E：幂等、一致性与 Gate 安全升级
- PR-F：adapter contract v1 与 conformance tests

## 8. 关键风险与缓解

- 风险：继续把重点放在 adapter 扩展，导致产品主线被“接更多生态”稀释
- 缓解：先完成事件模型和 evidence-first 控制台，再扩 adapter

- 风险：控制台功能增长快于审计模型，UI 变成不可解释的状态面板
- 缓解：所有新动作先定义事件与审计结构，再做交互

- 风险：自动化动作越来越多，但人类接管路径不清晰
- 缓解：把 `takeover / resume` 作为 P0 必做能力

- 风险：可靠性工作延期，导致展示层很好看但运行层不稳定
- 缓解：P1 明确聚焦 queue、retry、DLQ、reclaim、idempotency

## 9. 结论

AgentFlow 的护城河不是“我们也能调 agent 干活”，而是：

- 我们让多 Agent 执行过程变得可见
- 我们让自动化过程仍然在人类治理之下
- 我们让每一次推进都可解释、可追责、可恢复

所以路线图也应该围绕这条主线展开：

> 先做人机协作可视化，再做生产化可靠性，最后做生态和规模化。
