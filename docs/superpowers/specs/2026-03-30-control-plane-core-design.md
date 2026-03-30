# AgentFlow 控制面核心设计（单人多 Agent + 半自动调度）

日期：2026-03-30
状态：Draft v1（已完成设计评审对齐）

## 1. 设计目标

本设计聚焦 AgentFlow 第一阶段“控制面核心”，目标是让单人可以稳定管理多个 coding agent，并实现：

1. 问题发现定时化（Scheduler）
2. PR 评论事件驱动执行（Webhook）
3. 自动改代码并推 PR 更新
4. 严格项目门禁（门禁未通过不得推送）
5. 全链路可审计（任务状态 + run 记录）

## 2. 范围与边界

## 2.1 In Scope

- 单人多 Agent 协作（非多人权限系统）
- Hybrid 触发模型：定时发现 + 事件驱动执行
- 控制面状态机与并发治理（claim/lease/heartbeat/release/reclaim）
- Adapter 统一执行接口
- 项目级门禁执行与结果回写

## 2.2 Out of Scope（当前阶段）

- 团队级 RBAC 与组织协作权限
- 完整 SaaS 前端产品化
- 多租户隔离与账单系统
- 高阶模型路由优化（先保证控制面可控）

## 3. 方案选择

在候选方案中采用 **方案 A：Hybrid Control Plane**。

- 方案 A（推荐）：定时发现 + PR 评论事件 + 控制面治理 + 门禁闭环
- 方案 B：纯 GitHub Actions 编排（状态一致性不足）
- 方案 C：本地守护主导（可用性受本地在线影响）

选择 A 的原因：同时满足“半自动调度”“事件驱动执行”“可控并发”和“门禁闭环”，且保留平台无关性。

## 4. 架构分层

## 4.1 Ingress 层

- `Discovery Scheduler`：定时扫描 issue
- `PR Comment Webhook`：接收 `/agentflow ...` 指令

## 4.2 Control Core

- 任务状态机（任务生命周期）
- 租约管理（claim/heartbeat/release/reclaim）
- Run Ledger（执行实例账本）

## 4.3 Execution Layer

- Adapter Dispatcher（路由执行器）
- Workspace Runner（隔离工作目录）
- Safety Guard（高危命令防护）

## 4.4 Gate Layer

- 项目门禁配置
- 门禁执行器
- 推送前硬门禁判定

## 4.5 Sync & Feedback

- PR 评论回写（摘要、结果、失败原因）
- 任务状态同步
- 指标与报表输出

## 5. 事件与数据流

## 5.1 链路 A：定时发现（Issue Discovery）

1. 定时任务触发扫描
2. 拉取仓库 open issues（标签/更新时间/认领状态过滤）
3. 规则打分（priority/impact/effort/自动化可行性）
4. 写入任务表（`pending`）与状态历史
5. 命中自动准入规则则转 `approved`

## 5.2 链路 B：PR 评论驱动（Auto-Fix Run）

1. 接收 PR 评论命令（例如 `/agentflow run`）
2. 校验权限、命令合法性、幂等键
3. claim 任务并创建 run（状态置 `in_progress`）
4. 执行 adapter（拉分支、改代码、提交）
5. 执行项目门禁（测试/lint/build）
6. 门禁通过：push + 更新 PR + 回评论 + 状态推进
7. 门禁失败：不推送 + 回评论 + 置 `blocked`
8. release 租约并写审计

## 5.3 故障恢复

- lease 超时自动回收
- webhook 重放通过幂等键去重
- 可重试错误按策略重试
- 不可恢复错误进入 `blocked` 等待人工处理

## 6. 数据模型设计

在现有 `projects/tasks/status_history/links` 基础上扩展：

- `runs`：一次自动执行实例
- `run_steps`：执行过程分步日志
- `triggers`：触发来源与幂等键
- `gate_profiles`：项目门禁配置

## 6.1 runs 建议字段

- `id`, `task_id`, `project_id`
- `trigger_type`, `trigger_ref`
- `adapter`, `agent_name`, `workspace_ref`
- `status`（queued/running/passed/failed/canceled）
- `started_at`, `finished_at`
- `gate_passed`
- `result_summary`, `error_code`, `error_detail`
- `idempotency_key`（唯一）

## 7. 状态机与并发约束

任务主状态：
`pending -> approved -> in_progress -> pr_ready -> pr_open -> merged`
终态补充：`skipped`, `blocked`

强约束：

1. 仅 `pending/approved` 可 claim 为 `in_progress`
2. `in_progress` 必须持有有效 lease
3. 未通过门禁禁止推进到 `pr_ready/pr_open`
4. `merged/skipped` 为终态，不可再 claim
5. 每次状态变更必须写 `status_history`
6. 同一 task 同时最多一个 running run
7. 仅 owner agent 可 heartbeat/release

## 8. 门禁与安全

## 8.1 项目门禁配置（gate profile）

- `required_checks`（必过项）
- `commands`（白名单命令）
- `timeout_sec`
- `retry_policy`
- `artifact_policy`

## 8.2 执行规则

1. 隔离 workspace 执行
2. 按步骤执行门禁（prepare/test/lint/build）
3. 任一必需检查失败即阻断 push
4. 标准化输出 pass/fail 与关键日志

## 8.3 安全约束

- 命令白名单机制
- 高危命令拦截
- 最小权限凭据
- 日志脱敏
- `gate_passed=true` 才可 push/update PR

## 9. 测试策略

## 9.1 单元测试

- 状态转移合法性
- lease 与 reclaim
- 幂等键去重
- owner 权限校验

## 9.2 集成测试

1. 定时发现生成任务
2. 评论事件触发 run
3. 门禁通过后推送与回写
4. 门禁失败后 blocked 与回评论

## 9.3 混沌与回归

- 心跳丢失
- webhook 重放
- 网络失败重试
- 多 agent 并发冲突

## 10. 里程碑计划（4 阶段）

## M1（1 周）控制面稳定化

- 新表落库：runs/run_steps/triggers/gate_profiles
- 状态机与幂等约束完善
- run 生命周期查询能力

验收：连续 10+ run 无状态错乱

## M2（1 周）触发链路

- 定时发现器
- PR 评论 webhook 与命令解析

验收：双链路可触发且审计完整

## M3（1 周）门禁闭环

- 门禁配置与执行
- 失败阻断 push 并自动回写

验收：门禁失败不会污染目标分支

## M4（1 周）试运行与指标

- 2 个仓库 dogfood
- 指标上墙（成功率/阻塞率/处理时长/冲突率）

验收：20+ 任务实跑，collision < 5%

## 11. 上线门槛（Must Have）

1. 幂等与租约机制稳定
2. 审计链完整可追溯
3. 门禁失败绝不 push
4. webhook 重放不重复执行

## 12. 风险与缓解

1. 评论触发风暴
- 缓解：幂等键 + 限流 + 去抖

2. 门禁时长过长
- 缓解：分级门禁（快速门禁 + 完整门禁）

3. Adapter 行为差异
- 缓解：统一 AdapterResult 协议 + run_steps 标准化

4. 外部 API 不稳定
- 缓解：重试策略 + dead-letter 机制

## 13. 下一步

本设计确认后，下一阶段应进入 implementation planning：
- 数据库迁移计划
- webhook 服务接口定义
- 调度器任务拆分
- 门禁执行引擎拆分
- 验收测试清单

## 14. 会话连续性策略（新增）

为支持同一任务的多轮修改，控制面采用 **reuse-first** 会话策略：

1. 默认复用旧会话
- 同一 `task_id` 优先复用最近可用的 `session_id/thread_id`。
- 新一轮执行先加载上一次的 Context Pack（摘要、未完成项、关键文件、失败点、门禁记录）。

2. 新建会话判定条件（new-when-better）
- 目标变化导致上下文漂移明显；
- 会话过长导致质量或成本下降；
- 基线变化较大（大规模 rebase/重构）；
- 上一会话不可恢复（卡死、异常、失效）。

3. 新建会话必须继承上下文
- 即使新建会话，也必须附带最近 Context Pack，避免“从零开始”。

4. 并发安全
- 同一 `task_id` 同时只允许一个活跃会话持有 lease。
- 若旧会话未释放，需等待、回收或人工接管后再进入下一轮修改。
