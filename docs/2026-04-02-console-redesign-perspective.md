# AgentFlow Console 重设计思考：Agent 的 Jira，不是 Agent 的遥控器

日期：2026-04-02

## 核心类比

把 AgentFlow 想象成一家公司的 Jira：

- **Agent = 员工**。他们认领任务、执行工作、汇报进度、提交产出。
- **Human = 老板/经理**。他们看大盘、发现异常、做出干预决策、验收结果。
- **AgentFlow = Jira 本身**。提供看板、记录历史、强制流程规则。

在这个类比下，当前 Console 有几个根本性的设计错位。

---

## 当前问题：Console 是"操作面板"而不是"管理面板"

### 问题 1：老板不应该"Run Task"

当前的 Run Task 按钮让人类手动触发任务执行。这在 Jira 类比中相当于：

> 老板走进员工工位，抢过键盘帮他写代码。

Run Task 是**员工（Agent）的事**。老板只应该在一种情况下触发执行——"重试一个失败的任务"（retry），这本质上是一种**干预**，不是**执行**。

建议：
- 去掉"Run Task"按钮
- 如果需要保留，改名为"Retry"，只在任务 failed/blocked 时显示
- 真正的执行由 agent 通过 CLI/adapter 自动调度

### 问题 2：暴露了太多内部机制

当前 Task Detail 向人类展示了：

| 当前展示 | 谁关心 | 人类需要吗 |
|----------|--------|-----------|
| adapter 名称 | 系统 | 不需要 |
| agent name (内部标识) | 系统 | 不需要 |
| lease_until | 调度器 | 不需要，只需知道"是否卡住" |
| gate_passed (true/false) | 系统 | 需要知道"检查是否通过"，不需要原始字段 |
| idempotency key | 开发调试 | 不需要 |
| trigger_type | 系统 | 不需要 |

老板不需要知道员工用了什么工具（adapter），只需要知道**结果是什么、是否按时完成**。

### 问题 3：缺少老板真正关心的信息

老板打开 Jira 时，第一个问题是：**"有什么需要我处理的？"**

当前 Console 没有直接回答这个问题。老板需要自己翻看每个任务。

老板真正关心的：

1. **异常信号** — 哪些任务卡住了？哪些 gate 失败了？哪些长时间没有进展？
2. **交付健康度** — 今天完成了多少？平均交付周期多长？blocked 率是多少？
3. **需要决策的事项** — review 阶段有任务等待验收；blocked 任务需要决定是放弃还是继续
4. **趋势变化** — 比昨天好了还是差了？

### 问题 4：任务详情是"数据堆砌"而非"叙事"

当前 Task Detail 把所有数据平铺：stats、signals、PR links、timeline、runs……

老板看任务详情时，他想看到的是一个**故事**：

> "这个任务是 #42，三天前从 GitHub issue 创建。Agent-A 认领后开始执行，
> 完成了代码编写并提交了 PR #128，gate 检查通过，目前在 review 阶段等待验收。
> 过程中出现过一次 scope 变更（risk signal），但已解决。"

而不是一堆离散的 label-value 对。

---

## 重新思考：Console 应该是什么样的

### 一句话定位

> Console 是给人类管理者看的**治理仪表盘**，不是给人类操作者用的**执行控制台**。

### 首页：Manager Dashboard（当前没有）

回答：**"现在情况怎么样？需要我关注什么？"**

```
┌─────────────────────────────────────────────┐
│  📊 Today's Overview                        │
│                                             │
│  ┌─ Done ─┐ ┌─ In Progress ─┐ ┌─ Blocked ─┐│
│  │   12   │ │      5         │ │    2 ⚠     ││
│  └────────┘ └────────────────┘ └────────────┘│
│                                             │
│  ⚠ Needs Attention (2)                      │
│  • Task #38 blocked — agent lease expired   │
│  • Task #41 — gate failed, 3rd retry        │
│                                             │
│  ✅ Waiting Review (3)                       │
│  • Task #42 Fix auth bug — PR #128 ready    │
│  • Task #35 Add metrics — PR #125 ready     │
│  • Task #37 Refactor API — PR #130 ready    │
└─────────────────────────────────────────────┘
```

### Stage Board：保持，但改卡片内容

当前的 stage board 方向是对的。但每个任务卡片应该展示**人类关心的摘要**，不是内部数据：

| 当前 | 应该 |
|------|------|
| `p2/i3/e2` | 优先级标签（高/中/低） |
| `assigned_agent` | 谁在做（agent 名称，人类可读） |
| 状态 badge | 最新活动摘要（"PR 已提交，等待 review"） |

### Task Detail：改成"任务故事"

不是数据堆砌，而是分层的叙事：

**第一层：结论**（一眼就看到关键信息）
- 任务标题 + 当前阶段
- 一句话摘要："Agent 完成了代码编写，PR #128 已提交，等待验收"
- 下一步：明确告诉人类需要做什么（"请验收 PR"）

**第二层：异常**（只有异常时才显示）
- Risk 信号
- Gate 失败记录
- 长时间无进展警告

**第三层：执行历史**（可展开查看）
- 时间线（已有，设计合理）
- PR 和链接（已有，保留）

### 人类可执行的动作

在 Jira 中，经理能做什么？

1. **调整优先级** — 这个任务更重要/不那么重要
2. **重新分配** — 换一个 agent 来做
3. **验收/打回** — review 阶段 approve 或 reject
4. **放弃任务** — 这个不做了
5. **添加上下文** — 给任务加备注帮助 agent 理解

注意：**没有"执行任务"这个动作**。

---

## 具体设计建议

### Actions 区域重构

| 当前动作 | 建议改为 | 触发条件 |
|----------|---------|---------|
| Run Task | Retry | 只在 failed/blocked 时显示 |
| Move (select + force) | Approve / Reject / Block | 根据 task 状态显示对应动作 |
| (无) | Add Note | 始终可用 |
| (无) | Reprioritize | 始终可用 |

### 状态感知的动作按钮

不是给用户一个通用的"select status + move"表单，而是根据任务当前状态，**只显示合理的操作**：

```
任务在 review 阶段：
  [✅ Approve] [↩️ Request Changes] [⛔ Block]

任务在 blocked 阶段：
  [🔄 Retry] [↩️ Reassign] [🗑️ Drop]

任务在 in_progress 阶段：
  [⚠️ Block] [📝 Add Note]
```

这比一个通用的 status select + move 按钮直观得多。

### Task Detail 分层展示

```
┌─ Task Header ──────────────────────────────┐
│ #42 Fix auth bug        [REVIEW]            │
│ Agent: openclaw-agent · Started: 2h ago     │
│ "PR submitted, awaiting human verification" │
├─────────────────────────────────────────────┤
│ ⚠ No issues — all checks passed             │
├─ Context ───────────────────────────────────┤
│ Source: GitHub Issue #88                     │
│ Repo: org/repo                              │
│ PR: #128 · Gate: passed                     │
├─ Actions ───────────────────────────────────┤
│ [✅ Approve] [↩️ Request Changes] [📝 Note] │
├─ Timeline ──────────────────────────────────┤
│ ● 14:30 run_completed — all steps passed    │
│ ● 14:15 gate_passed — lint + test           │
│ ● 13:00 task_claimed — by openclaw-agent    │
│ ● 12:00 status_change — ready → in_progress│
└─────────────────────────────────────────────┘
```

---

## 当前合理、应该保留的部分

1. **Stage Board 的方向** — 按 stage 分组的看板是正确的 Jira 式设计
2. **Ledger 事件驱动** — 所有变更可追溯，这是 Jira 的 Activity Log
3. **SSE 实时更新** — 让管理者实时看到变化
4. **Audit Trail** — 底部的审计面板方向正确
5. **Force move 机制** — 保留但作为高级操作，默认隐藏

---

## 总结

| 维度 | 当前 Console | 应该是 |
|------|-------------|--------|
| 定位 | Agent 的遥控器 | Agent 工作的可视化治理面板 |
| 首页 | 直接是任务列表 | 管理者仪表盘 + 异常提醒 |
| 核心动作 | Run Task + Move | 状态感知的干预按钮 |
| 信息密度 | 所有数据平铺 | 分层：结论 → 异常 → 详情 |
| 人类角色 | 操作者 | 监督者 |
| 设计参考 | 运维工具 | Jira / Linear / GitHub Projects |

一句话：**让老板看到他需要关心的事，让老板做出他需要做的决策，其他都交给系统。**
