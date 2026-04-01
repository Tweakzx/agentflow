# AgentFlow 90 天生产化路线图（P0/P1/P2）

日期：2026-04-01

## 1. 目标与定位

目标是在 90 天内将 AgentFlow 从“可运行的控制插件”升级为“团队可依赖的 Agent 控制面（Control Plane）”，满足可用性、安全性、可审计性与规模化演进要求。

一句话定位：

> AgentFlow = 面向多 Agent 研发执行的控制面，提供任务治理、门禁、安全并发和可审计交付。

## 2. Go/No-Go 生产化门槛（硬指标）

上线前统一以下 6 个硬指标：

- 任务冲突率（collision）`< 2%`
- 重复执行率（duplicate run）`< 1%`
- 门禁误放行率（false pass）`= 0`
- 任务从 claim 到首次进度回写 `P95 < 8 分钟`
- webhook 幂等正确率 `= 100%`
- 审计追溯完整率 `= 100%`（每次状态变更都有 run/trigger 关联）

说明：可基于现有 MVP 指标体系扩展为生产 SLO 周报。

## 3. 90 天路线图

## P0（第 1-3 周）：稳定性与安全底座

目标：先“稳”和“可控”，再扩生态。

### P0-1 任务执行可靠性

- 引入 `queued` 状态与统一 job runner（避免 webhook 请求线程直接执行任务）
- 增加重试策略（指数退避）
- 增加死信队列（DLQ）
- 增加 lease reclaim 守护任务（定时回收超时 `in_progress`）

验收：

- 失败任务可重试并带 attempt 记录
- 超过重试阈值任务进入 DLQ 可观测
- reclaim 任务每周期有统计输出

### P0-2 幂等与一致性加固

- 统一入口幂等键规则：`comment / schedule / manual`
- run、trigger、task transition 建立强一致关联（`run_id` 全链路贯通）
- 增加“同一 task 同时仅一个 running run”数据库约束/事务锁

验收：

- webhook 重放不会触发重复执行
- 任意状态变更可追溯 trigger 与 run
- 并发触发下无双 running run

### P0-3 Gate 安全升级（重点）

- Gate 从自由字符串命令升级为结构化命令模板（`command + args`）
- 默认启用 allowlist（拒绝非白名单）
- 提供策略模板：`strict / fast / solo`

验收：

- 默认策略下非白名单命令不可执行
- Gate 配置可审计（策略、命令模板、更新时间）

### P0-4 基础可运维性

- 健康检查：`/healthz`、`/readyz`
- 指标：`run_success_rate`、`gate_fail_rate`、`queue_depth`、`reclaim_count`
- 结构化日志（JSON）+ `trace_id`（task/run 贯穿）

验收：

- 部署后可被探针和监控系统接入
- 关键流程具备最小排障信息

## P1（第 4-8 周）：能力扩展与团队可用

目标：从“单机可用”到“团队可用”。

### P1-1 Adapter 标准化（核心产品化）

- 固化 `adapter contract v1`：`discover/create/update/sync/run`
- 除 OpenClaw 外，再交付至少 1 个主流生态 adapter
- 建立 adapter conformance tests（统一回归）

### P1-2 控制台升级

在现有 Stage Board / Recent Runs / Audit 基础上新增：

- 异常中心（失败聚合，按 `error_code` 分组）
- 人工接管（`takeover / reassign / force move`）
- run 详情 drill-down（step 日志 + gate 输出）

### P1-3 规则与策略层

- 项目级策略：自动准入、风险分级、必需审批人
- 任务路由：按类型/标签分配 agent 或 adapter
- timebox 策略：超时自动降级/转人工

### P1-4 测试与发布工程化

- 消除环境路径硬编码，保证任意环境可跑
- PR 阻断流水线：单测 + 集成 + e2e
- 执行一次 chaos day（webhook 重放、网络抖动、gate 超时）

## P2（第 9-12 周）：商业化与规模化

目标：从“工具”升级为“平台能力”。

### P2-1 AgentOps 指标产品化

- 指标：lead time、blocked rate、reclaim frequency、collision rate
- 维度：repo / agent / provider
- 周报自动化推送（Slack/飞书）

### P2-2 多租户与权限

- RBAC（viewer/operator/admin）
- 项目级隔离、凭据隔离
- 审计不可篡改导出（合规）

### P2-3 高可用部署

- SQLite -> Postgres（保留本地模式）
- worker 水平扩展
- 灰度发布 + 回滚策略

## 4. 本周行动清单（可直接执行）

- 定义 `adapter contract v1`（文档 + JSON Schema）
- 新增 `queue + retry + dead-letter` 三张表
- Gate 增加 strict 模式并默认拒绝非 allowlist
- 修复测试路径硬编码并确保 CI 在容器路径通过
- 控制台新增“异常任务视图”
- 每周固定输出 6 个 SLO 指标

## 5. 建议拆分为独立 PR 的执行顺序

- PR-A：文档与 SLO 定义（本文件 + 指标口径）
- PR-B：queue/retry/DLQ 与 job runner
- PR-C：幂等/一致性约束与审计链路贯通
- PR-D：Gate 策略模板 + allowlist 默认化
- PR-E：控制台异常中心 + 接管操作

## 6. 风险与缓解

- 风险：过早扩 adapter，底层可靠性不足导致失败率高
- 缓解：严格执行“P0 先于 P1”

- 风险：指标定义不统一导致跨周数据不可比
- 缓解：先固化字段、口径与统计窗口

- 风险：控制台功能扩展快于审计模型
- 缓解：所有动作先定义审计事件再落 UI
