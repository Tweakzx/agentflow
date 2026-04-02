# AgentFlow Event Model v1 设计

日期：2026-04-02
状态：Draft v1

## 1. 目标

本设计定义 AgentFlow 的 `event model v1`，目标是把当前分散在任务状态、运行步骤、审计记录和 SSE 推送里的过程信息，统一为一套前后端共用的领域事件账本。

一句话目标：

> 让 AgentFlow 中每一次自动动作、人工动作、状态推进和失败恢复，都先成为结构化事件，再成为任务和运行的当前状态。

本设计要解决的核心问题：

1. 同一个任务的“发生了什么”目前分散在多处记录中，前端难以解释
2. 状态变化常常只有结果，没有足够证据说明原因
3. SSE、Audit、Run Detail 各自使用不同模型，无法形成统一心智
4. 后续的接管、重派、恢复自动、风险视图，都需要统一事件语义

## 2. 设计结论

采用：**统一领域事件账本 + 当前态快照表**

- `ledger_events`：唯一事实来源，记录发生过的事情
- `tasks`：任务当前状态快照
- `runs`：运行当前状态快照

不采用“事件只做 API 包装”的原因：

- 这会把问题继续留在存储层，前后端仍然会面对多套不一致语义
- 接下来控制台要做 evidence-first 展示，必须先有统一事实模型
- 当前历史包袱较小，适合直接建立正确模型，而不是先做兼容层

## 3. 核心原则

1. 事件先于状态
- 任何状态变化必须先写事件，再更新快照表。

2. 证据先于结论
- 自动化动作不能只写“成功/失败”，必须附带可展示给人的证据。

3. 一个动作，一条主事件
- 一个业务动作应有明确主事件，避免同一动作被拆成无法关联的零碎记录。

4. 快照服务于查询
- `tasks/runs` 保留为快照表，用于列表、筛选、claim、lease、当前态读取。

5. 事件服务于解释与审计
- 时间线、审计、SSE、风险聚合、人工接管都应围绕统一事件读取。

## 4. 数据模型边界

## 4.1 ledger_events 的职责

`ledger_events` 负责记录：

- 任务认领、释放、重派、接管
- run 开始、结束、失败
- step 执行进展
- gate 结果
- 冲突、阻塞、恢复
- 人工强制流转
- webhook / scheduler / manual 触发结果
- handoff 与 progress 摘要

它不负责：

- 替代 `tasks` 做高频当前状态查询
- 替代 `runs` 做当前运行聚合统计

## 4.2 tasks 的职责

`tasks` 继续作为任务当前态快照，保存：

- 当前 `status`
- 当前 `assigned_agent`
- 当前 `lease_until`
- 当前 `branch` / `pr_url`
- 基础排序字段：`priority/impact/effort`

## 4.3 runs 的职责

`runs` 继续作为运行当前态快照，保存：

- 当前 `status`
- 当前 `adapter`
- 当前 `agent_name`
- 当前 `gate_passed`
- 当前 `result_summary`
- 当前 `error_code`
- 开始/结束时间

## 5. 统一事件表 schema

建议新增主表：`ledger_events`

```sql
CREATE TABLE IF NOT EXISTS ledger_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL,
    task_id INTEGER,
    run_id INTEGER,
    trigger_id INTEGER,
    parent_event_id INTEGER,
    event_family TEXT NOT NULL,
    event_type TEXT NOT NULL,
    actor_type TEXT NOT NULL,
    actor_id TEXT,
    source_type TEXT,
    source_ref TEXT,
    status_from TEXT,
    status_to TEXT,
    run_status_from TEXT,
    run_status_to TEXT,
    severity TEXT NOT NULL DEFAULT 'info',
    summary TEXT NOT NULL,
    evidence_json TEXT NOT NULL DEFAULT '{}',
    next_action_json TEXT NOT NULL DEFAULT '{}',
    context_json TEXT NOT NULL DEFAULT '{}',
    idempotency_key TEXT,
    occurred_at TEXT NOT NULL DEFAULT (datetime('now')),
    recorded_at TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY(project_id) REFERENCES projects(id) ON DELETE CASCADE,
    FOREIGN KEY(task_id) REFERENCES tasks(id) ON DELETE SET NULL,
    FOREIGN KEY(run_id) REFERENCES runs(id) ON DELETE SET NULL,
    FOREIGN KEY(trigger_id) REFERENCES triggers(id) ON DELETE SET NULL,
    FOREIGN KEY(parent_event_id) REFERENCES ledger_events(id) ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS idx_ledger_events_project_id_id
ON ledger_events(project_id, id);

CREATE INDEX IF NOT EXISTS idx_ledger_events_task_id_id
ON ledger_events(task_id, id);

CREATE INDEX IF NOT EXISTS idx_ledger_events_run_id_id
ON ledger_events(run_id, id);

CREATE INDEX IF NOT EXISTS idx_ledger_events_family_type
ON ledger_events(event_family, event_type);

CREATE INDEX IF NOT EXISTS idx_ledger_events_occurred_at
ON ledger_events(occurred_at, id);
```

## 6. 字段语义

### 6.1 关联字段

- `project_id`：事件所属项目
- `task_id`：事件所属任务，可为空
- `run_id`：事件所属运行，可为空
- `trigger_id`：事件关联的触发记录，可为空
- `parent_event_id`：用于把步骤事件、恢复事件挂到主事件下

### 6.2 分类字段

- `event_family`：高层分类，便于前端聚合
- `event_type`：具体事件名，便于程序判断

### 6.3 行为者字段

- `actor_type`：如 `agent`、`human`、`system`、`webhook`
- `actor_id`：如 `codex-a`、`web-console-user`、`scheduler`

### 6.4 状态字段

- `status_from/status_to`：任务状态变化
- `run_status_from/run_status_to`：运行状态变化

### 6.5 展示字段

- `summary`：给人直接看的短摘要
- `severity`：`info / warning / error`
- `evidence_json`：证据包
- `next_action_json`：建议的人类下一步动作
- `context_json`：补充上下文，不直接当主展示字段

### 6.6 时间字段

- `occurred_at`：事件真实发生时间
- `recorded_at`：写入账本时间

## 7. 事件分类与命名

建议固定 5 个 `event_family`：

1. `dispatch`
- 谁把任务交给谁，谁接管了谁

2. `execution`
- run 与 step 的执行过程

3. `governance`
- 状态流转、lease、force move、reclaim

4. `feedback`
- progress、handoff、comment、同步回写

5. `risk`
- gate failed、conflict、blocked、dead-letter

建议的 `event_type` 首批枚举：

### dispatch

- `task.claimed`
- `task.released`
- `task.reassigned`
- `task.takeover_started`
- `task.automation_resumed`

### execution

- `run.started`
- `run.finished`
- `step.started`
- `step.passed`
- `step.failed`

### governance

- `task.status_changed`
- `lease.extended`
- `lease.reclaimed`
- `task.force_moved`

### feedback

- `progress.reported`
- `handoff.recorded`
- `comment.received`
- `comment.published`
- `pr.synced`

### risk

- `gate.failed`
- `gate.passed`
- `task.blocked`
- `task.conflict_detected`
- `run.dead_lettered`

命名规则：

- 使用 `domain.action` 形式
- 避免 UI 名词直接进入事件名
- 事件名表示“发生过什么”，不是“界面如何展示”

## 8. 证据包结构

`evidence_json` 是本设计最重要的字段，建议至少支持以下结构：

```json
{
  "step_name": "gate",
  "error_code": "gate_failed",
  "log_excerpt": "pytest failed in tests/test_runner.py",
  "commands": ["pytest -q"],
  "files": ["tests/test_runner.py"],
  "links": {
    "issue_url": "https://github.com/org/repo/issues/12",
    "pr_url": "https://github.com/org/repo/pull/34"
  },
  "metrics": {
    "duration_ms": 18342
  }
}
```

约束：

- `summary` 必须可单独阅读
- `evidence_json` 必须能解释“为什么会有这条事件”
- 不要求保存完整日志，但要能保存关键摘录和定位信息

## 9. 建议动作结构

`next_action_json` 用于把“人接下来能做什么”直接挂在事件上：

```json
{
  "recommended": "retry_gate",
  "actions": [
    { "id": "retry_run", "label": "Retry Run" },
    { "id": "takeover", "label": "Take Over" },
    { "id": "move_ready", "label": "Move Back To Ready" }
  ]
}
```

它的意义不是立刻驱动按钮实现，而是先保证事件模型能承载“可接管”的产品方向。

## 10. 写入规则

## 10.1 总规则

所有会改变任务理解、执行进展或人机责任边界的动作，都必须写入 `ledger_events`。

## 10.2 事务顺序

建议统一为：

1. 创建主事件
2. 更新 `tasks` 或 `runs` 快照
3. 如需要，补充附属事件
4. 提交事务

即：

`domain action -> ledger event -> snapshot update -> commit`

而不是：

`snapshot update -> 事后补事件`

## 10.3 各类动作的强约束

### 任务状态变化

- 必须写 `task.status_changed`
- 如果是自动流转，必须附带 `evidence_json`
- 如果是人工强制流转，必须写 `task.force_moved`

### claim / release / heartbeat / reclaim

- claim 写 `task.claimed`
- release 写 `task.released`
- heartbeat 写 `lease.extended`
- reclaim 写 `lease.reclaimed`

### run 生命周期

- run 创建时写 `run.started`
- run 结束时写 `run.finished`
- 关键步骤至少写 `step.started` + `step.passed/failed`

### gate

- gate 通过写 `gate.passed`
- gate 失败写 `gate.failed`
- gate 失败导致任务阻塞时，额外写 `task.blocked`

### 人工动作

- 接管写 `task.takeover_started`
- 恢复自动写 `task.automation_resumed`
- 重派写 `task.reassigned`

## 11. 当前代码路径的映射建议

## 11.1 Store 层

新增：

- `append_ledger_event(...)`
- `list_ledger_events(...)`
- `list_task_timeline(task_id, ...)`
- `list_run_timeline(run_id, ...)`

弱化：

- `append_event(...)`
- `list_events_since(...)`
- `list_recent_status_history(...)`
- `list_run_steps(...)`

## 11.2 Runner 层

当前 `Runner` 中已有：

- `create_run`
- `append_run_step`
- `finalize_run`
- `move_task`

建议改为：

- `create_run` 后立即写 `run.started`
- claim 后写 `task.claimed`
- 每个步骤改为写标准 `step.*` 事件
- gate 结果改为写 `gate.passed` 或 `gate.failed`
- 任务推进改为写 `task.status_changed`

## 11.3 Webhook 层

当前评论触发路径中已存在：

- trigger 注册
- task 查找/创建
- runner 执行

建议新增：

- 收到评论时写 `comment.received`
- 若命中重复幂等，写 `comment.received` 或 `trigger.duplicate_ignored`
- 触发 run 时写 `run.started`

## 12. API 与 SSE 契约

## 12.1 统一事件对象

后端对外统一返回：

```json
{
  "id": 101,
  "project": "demo",
  "task_id": 12,
  "run_id": 33,
  "trigger_id": 7,
  "event_family": "risk",
  "event_type": "gate.failed",
  "actor_type": "system",
  "actor_id": "gate-evaluator",
  "status_from": "in_progress",
  "status_to": "blocked",
  "run_status_from": "running",
  "run_status_to": "failed",
  "severity": "error",
  "summary": "Gate failed on pytest -q",
  "evidence": {
    "step_name": "gate",
    "error_code": "gate_failed",
    "log_excerpt": "2 tests failed"
  },
  "next_action": {
    "recommended": "takeover"
  },
  "occurred_at": "2026-04-02 10:00:00",
  "recorded_at": "2026-04-02 10:00:01"
}
```

## 12.2 SSE

`GET /api/events` 应直接返回标准事件流，而不是通用 `event + payload` 包裹。

前端不再需要知道：

- 这是 `status_history` 变出来的
- 还是 `run_steps` 投影出来的
- 还是独立 `events` 表推出来的

前端只需要知道：

- 来了一条新事件
- 它属于哪个任务/运行
- 应该展示什么摘要和证据

## 12.3 任务详情 API

任务详情建议直接返回：

- `task`：当前快照
- `timeline`：该任务最近 N 条 `ledger_events`
- `recent_runs`：运行快照
- `derived_summary`：从事件聚合出的最近进度、最近失败、推荐动作

## 13. 前端消费模型

控制台按统一事件模型消费：

### Stage Board

读取 `tasks` 快照，但卡片角标从最新事件派生：

- 最近活动时间
- 最近风险事件
- 最近 progress/handoff 摘要

### Task Detail

直接围绕 `timeline` 展示：

- 当前状态
- 最近 run
- 最近 progress
- 最近 handoff
- 最近风险
- 建议动作

### Recent Runs

仍以 `runs` 为列表入口，但点击后展开该 run 对应事件时间线。

### Audit Trail

不再单独依赖 `status_history`，而是 `ledger_events` 的过滤视图。

## 14. 与旧模型的关系

由于当前历史负担不大，建议采用更直接的迁移策略：

1. 新增 `ledger_events`
2. 新写路径直接以 `ledger_events` 为主
3. `status_history/run_steps/events` 可短期保留，作为过渡期兼容读写
4. 待控制台和 API 全部切换后，再评估是否保留为投影表

本设计不要求一开始就完全删除旧表，但要求从 v1 起：

> 新功能只能基于统一事件账本设计，不再扩展旧事件模型。

## 15. 验收标准

1. 任一任务的状态变化都能找到对应 `ledger_events`
2. 任一 `blocked` 任务都能在单条事件上看到失败摘要与证据
3. SSE、任务时间线、审计列表读取同一事件对象模型
4. 人工接管、恢复自动、重派都能作为标准事件显示
5. 前端无需拼接 `status_history + run_steps + events` 才能解释一条任务时间线

## 16. 风险与取舍

### 风险 1：一次性改动路径较多

缓解：

- 保留 `tasks/runs` 快照表
- 优先重构写路径，再切换读路径

### 风险 2：事件写得太细，前端时间线噪音过多

缓解：

- 用 `event_family` 和 `parent_event_id` 支持聚合
- 明确“一个动作一条主事件”的原则

### 风险 3：事件证据格式失控

缓解：

- 先约束 `evidence_json` 的推荐字段
- 后续再补 JSON Schema

## 17. 下一步

本设计确认后，下一阶段应进入 implementation planning：

1. 数据库迁移计划：新增 `ledger_events`
2. Store API 设计：事件写入与查询接口
3. Runner / Webhook 写路径改造
4. SSE 与任务详情 API 切换
5. 控制台 Evidence-first 时间线实现
