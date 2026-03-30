# AgentFlow 最终呈现设计（插件入口 + Web 控制台）

日期：2026-03-30
状态：Draft v1（已与用户对齐）

## 1. 目标与定位

本设计定义 AgentFlow 在用户侧“最终看起来是什么样”，并回答：
- 作为 Agent 插件如何被使用
- Web 控制台如何承载执行管理
- 控制面如何把自动化过程变成可观测、可接管、可追责

范围基于：
- 单人多 Agent
- 半自动调度
- 问题发现定时化
- PR 评论事件驱动执行
- 自动改代码并推 PR 更新（受项目门禁约束）

## 2. 呈现总览（四个入口）

1. Agent 内命令入口
- 在 OpenClaw/Codex/Claude Code 中使用统一命令
- 例如：`/agentflow run`, `/agentflow status`, `/agentflow next`

2. GitHub 交互面
- PR 评论触发执行（如 `/agentflow run`）
- 自动回评论：执行摘要、门禁结果、下一步建议

3. 本地/运维 CLI
- `agentflow claim-next/workers/run-once/run-batch/stats`
- 用于排障、恢复、维护

4. 可视化 Web 控制台（本设计重点）
- 任务中心优先（Task-first）
- 运行细节通过 Run 抽屉呈现

## 3. 信息架构选择

采用：**方案 A（Task-first + Run 抽屉）**

- 左：任务列表
- 中：任务详情
- 右：Run 时间线抽屉

选择原因：
- 以“问题推进”作为主心智，符合任务管理习惯
- 同时保留执行排障能力（无需跳页）

## 4. 页面结构（V1）

## 4.1 全局框架

- 顶栏：项目切换、环境标识、全局搜索、告警入口
- 左栏：Task Queue
- 主区：Task Detail
- 右抽屉：Run Timeline Drawer（可展开/收起）

## 4.2 Task Queue（首页）

字段：
- `task_id`
- `title`
- `status`
- `priority/impact/effort`
- `assigned_agent`
- `lease_until`
- `last_run_status`
- `gate_status`
- `updated_at`

能力：
- 快捷筛选：待处理/进行中/阻塞/门禁失败/等待人工
- 排序：优先级、更新时间、失败次数
- 批量动作：批准、暂停、重新调度

## 4.3 Task Detail（主工作面）

模块：
- TaskHeaderCard（标题、主状态、关联 issue/PR）
- StateTransitionBar（状态机可视化）
- TaskMetaPanel（触发来源、租约、适配器、最近门禁）
- ActionPanel（触发运行/人工接管/重跑门禁/阻塞切换）
- AuditTimeline（状态变化审计）

## 4.4 Run Timeline Drawer（右抽屉）

步骤模型：
- `claim -> checkout -> edit -> gate -> push -> comment`

每步展示：
- 状态、耗时、关键日志、失败码

动作：
- 重试本次 run
- 从失败步骤续跑
- 查看完整日志

## 4.5 辅助页面

- Execution Ops（非首页）：ActiveWorkers、LeaseMonitor、RetryQueue、DeadLetter
- Gate Profiles：项目门禁配置与 dry-run

## 5. 核心交互流程

## 5.1 PR 评论触发成功路径

1. 用户 PR 评论 `/agentflow run`
2. 任务进入 `in_progress` 并高亮
3. Run 抽屉实时追加步骤日志
4. 门禁通过后自动推送更新
5. 任务推进到 `pr_ready/pr_open` 并回评论

## 5.2 门禁失败路径

1. `gate` 步骤失败
2. 任务标记 `blocked`（或 `gate_failed`）
3. Task Detail 显示失败门禁项与摘要日志
4. 用户可选：重试运行 / 人工接管

## 5.3 租约超时与回收

1. 心跳中断导致 lease 到期
2. UI 显示“已回收”
3. 任务回到可 claim 队列
4. 支持一键重调度

## 5.4 人工接管

1. 点击“人工接管”
2. 状态置 `blocked(manual)`，暂停自动流程
3. 审计记录操作者
4. 可“恢复自动”回 `approved`

## 6. 数据绑定要求（UI 需要）

Task 关键字段：
- `source_type/source_ref`
- `linked_issue/linked_pr`
- `current_run_id`
- `block_reason`
- `idempotency_key(last_trigger)`

Run 关键字段：
- `run_id`, `trigger_type`, `trigger_ref`
- `adapter`, `agent_name`
- `started_at`, `finished_at`, `duration_ms`
- `status`, `gate_passed`

Step 关键字段：
- `step_name`
- `status`
- `started_at`, `ended_at`
- `log_excerpt`
- `error_code`

## 7. 非功能要求

1. 实时性
- Run 日志延迟 <= 3 秒（轮询或 SSE）

2. 一致性
- webhook 至少一次送达
- 幂等保证避免重复执行结果

3. 安全
- 前端不直接持有高权限 token
- 敏感日志脱敏

4. 性能
- 列表 1k 任务以内筛选/分页 < 500ms

5. 可审计
- 按钮操作与自动动作均写审计记录

## 8. 交付计划（UI/后端联动）

## Iteration 1（骨架可用）

- Task Queue + Task Detail 基础页面
- Run 抽屉（静态日志）
- 手动触发运行按钮

## Iteration 2（执行闭环）

- Webhook 事件联动状态刷新
- 门禁结果可视化
- 重试与人工接管动作可用

## Iteration 3（运维增强）

- Lease 监控、Dead-letter、批量操作
- 指标卡片（throughput/blocked rate/gate pass rate）

## 9. 验收标准

1. PR 评论触发后，UI 能完整展示状态推进路径
2. 门禁失败可定位失败步骤并给出摘要
3. 超时回收、重试、接管可闭环执行
4. 审计时间线完整且支持筛选

## 10. 设计结论

AgentFlow 的最终呈现不是“另一个聊天界面”，而是：
- 以任务推进为中心
- 以 run 细节为可观测底座
- 以门禁与审计为控制面护栏

该形态能兼顾“自动化效率”和“工程可控性”，符合单人多 Agent 的实际落地需求。

## 11. 会话体验原则（新增）

为减少重复沟通和上下文丢失，前端与控制面应体现：

1. 默认复用旧会话（reuse-first）
- 同一任务再次触发时，优先显示并续用历史会话上下文。

2. 新建会话需有明确理由
- 页面展示“为何新建”（如上下文漂移、会话失效、基线变化）。

3. 新会话继承旧摘要
- UI 在任务详情中展示“继承上下文包”，便于用户确认连续性。

## 12. 实施快照（2026-03-30）

当前已具备的可操作链路：

1. Task-first 执行闭环（CLI）
- 任务创建/认领/执行/门禁/阻塞/审计均可从 CLI 触发与追踪。

2. 运行可观测
- `runs` / `run-steps` 可查看执行实例与步骤日志摘要。

3. 触发可观测
- `triggers` 可查看幂等触发记录。

4. 双入口触发
- `discover-issues` 支持定时发现数据接入。
- `handle-comment` 支持评论事件数据接入并执行 `/agentflow run`。
