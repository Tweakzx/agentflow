# AgentFlow 与 Harness Engineering：设计反思与改进分析

日期：2026-04-02

基于三篇文章的深度阅读：
1. OpenAI, "Harness engineering: leveraging Codex in an agent-first world" (2026-02-11)
2. Anthropic, "Effective harnesses for long-running agents" (2025-11-26)
3. Anthropic, "Harness design for long-running application development" (2026-03-24)

---

## 第一部分：Harness Engineering 到底在说什么

### 1.1 三篇文章各解决什么问题

**文章 1（OpenAI）—— 工程师角色的根本转变**

OpenAI 的团队用 Codex 从零构建了一个真实产品（100 万行代码、1500+ PR、3 名工程师）。文章的核心不是 "Codex 多厉害"，而是一个发现：

> 当工程师不再写代码，他们的核心工作变成了**设计让 Agent 能高效工作的环境**。

这个"环境"包括：
- 把项目知识编码到仓库中（`AGENTS.md` 作为目录，`docs/` 作为结构化知识库）
- 用自定义 linter 和 CI 机械化执行架构约束
- 让 Agent 能直接操作 UI（Chrome DevTools Protocol）和查询指标（LogQL/PromQL）
- 用后台 Agent 持续清理技术债务（"垃圾回收"）

OpenAI 把这种工作称为 **harness engineering**——设计和维护 Agent 工作环境的工程。

**文章 2（Anthropic）—— 跨 Session 连续性的具体解法**

Anthropic 发现了一个具体问题：Agent 在多个 context window 之间无法保持连贯。表现有两种：
1. **一次做太多**：Agent 试图一次性完成所有功能，中途耗尽上下文，留下半成品
2. **过早宣布完成**：Agent 看到已有进展就宣布任务完成，实际功能并不完整

解法是一个具体的两阶段 harness：
- **Initializer Agent**：第一次运行时创建 `init.sh`、`claude-progress.txt`、`feature_list.json`
- **Coding Agent**：后续每次 session 读取 progress → 选一个 feature → 增量实现 → commit + 更新 progress

关键的三个设计决策：
1. **Feature list 用 JSON 不用 Markdown**——Agent 更不容易擅自修改 JSON 中的验收标准
2. **每次 session 必须先恢复上下文**——读 progress file、读 git log、启动 dev server 验证基本功能
3. **增量进展**——每次只做一个 feature，做完再接下一个

**文章 3（Anthropic）—— Generator-Evaluator 分离**

这篇文章发现了两个更深层的 Agent 失败模式：
1. **Context Anxiety**：模型感知到上下文快满了，开始草率收尾。解法是 context reset——清空上下文，用结构化的 handoff artifact 接力
2. **Self-evaluation Bias**：Agent 对自己的产出评价严重偏向正面。解法是独立的 Evaluator Agent

由此构建了三 Agent 架构：
- **Planner**：将简短需求展开为完整产品规格
- **Generator**：逐 feature 实现，每个 sprint 与 Evaluator 协商"完成标准"
- **Evaluator**：用 Playwright 做真实用户级测试，给出结构化评分和修复建议

文章还给出了一个重要的迭代教训：**随着模型能力提升（Opus 4.5 → 4.6），harness 应该简化**。Sprint 拆分和 context reset 在 4.5 上是必须的，在 4.6 上可以移除。但 Evaluator 在任务接近模型能力边界时仍然有价值。

### 1.2 三篇文章的共同内核

剥离具体的实现细节，三篇文章在说同一件事：

> **Harness 是一套具体的管理 Agent 工作行为的组件。它解决五个核心问题：**

| 编号 | 问题 | 三篇文章的共同解法 |
|------|------|-------------------|
| C1 | Agent 不知道从哪开始 | 提供结构化的上下文：progress file、feature list、docs/ 知识库 |
| C2 | Agent 一次想做太多 | 把工作拆成增量步骤：逐 feature 实现、sprint contract |
| C3 | Agent 做完不知道是否真的完成 | 独立验证：evaluator agent、端到端测试、acceptance criteria |
| C4 | Agent 换了一个 session 就失忆 | 结构化交接：handoff artifact、git commit、progress file |
| C5 | Agent 的行为需要持续修正 | 持续反馈循环：linter 强制规范、doc gardening、golden principles |

**Harness 不关心是单个任务还是多个任务。** OpenAI 管了 1500+ PRs，Anthropic 的 feature list 有 200+ 项。Harness 关心的是：**不管 Agent 做什么任务，它都有足够的上下文、明确的标准、和可靠的交接机制。**

---

## 第二部分：AgentFlow 当前能力的逐项检视

### 2.1 AgentFlow 是什么

AgentFlow 是一个管理多 Agent 任务执行的系统。它的核心组件：

| 组件 | 文件 | 职责 |
|------|------|------|
| Task FSM | `store.py` + `schema.py` | 任务状态机：todo → ready → in_progress → review → done |
| Runner | `services/runner.py` | 任务调度和执行编排 |
| Ledger | `services/ledger.py` | 事件审计（5 个 event family、20+ event type） |
| Gates | `services/gates.py` | 质量门禁（执行 shell 命令） |
| Adapter | `adapters/base.py` | Agent 接入接口 |
| Console | `console.py` + web/ | 可视化治理界面 |
| Triggers | `services/triggers.py` | 事件触发器 |
| Discovery | `services/discovery.py` | 外部 Issue 导入 |

### 2.2 用 Harness 的五个核心问题检视 AgentFlow

#### C1：Agent 是否有足够的上下文

**当前状态**：Agent 认领任务时，通过 `AdapterContext` 获得：

```python
class AdapterContext:
    task: Task                    # 标题、描述、优先级
    project: str                  # 项目名
    repo_full_name: str | None    # 仓库名
    previous_runs: list[dict]     # 最近 5 次运行记录
    gate_profile: dict | None     # Gate 配置
```

OpenClaw adapter 的 `_build_prompt` 将这些信息组装成 prompt（[openclaw.py:90-134](src/agentflow/adapters/openclaw.py#L90-L134)）。

**差距**：

| 缺失的上下文 | 三篇文章的对应 | 对 Agent 的影响 |
|-------------|--------------|----------------|
| 项目的架构约束和编码规范 | OpenAI 的 `AGENTS.md` + linter 错误消息中嵌入修复指引 | Agent 不知道项目的边界规则 |
| 历史决策和设计记录 | OpenAI 的 `docs/design-docs/` 和 `docs/exec-plans/` | Agent 重复探索已解决的问题 |
| 前序 Agent 的交接信息 | Anthropic 的 `claude-progress.txt` | Agent 无法从前人工作基础上继续 |
| 验收标准 | Anthropic 的 `feature_list.json` | Agent 不清楚"完成"意味着什么 |

**判断**：C1 严重不足。Agent 拿到的上下文只有任务本身（标题、描述、优先级），缺少项目的规则、历史、和验收标准。

#### C2：工作是否被合理拆分

**当前状态**：AgentFlow 有完整的任务拆分机制：
- 每个 Task 是独立的原子工作单元
- Task 有评分公式 `(priority * 2 + impact * 3) / effort` 决定优先级
- `claim_next_task` 自动按评分选取下一个任务
- Run 和 Run Step 提供执行过程的分步记录

**差距**：不在于拆分机制本身，而在于**单个任务内部的粒度控制**。三篇文章都强调"一次只做一件事"——Anthropic 用 feature list 强制一次一个 feature，OpenAI 用 PR 粒度控制。AgentFlow 没有对 Agent 在一个 Run 内应该做多少施加任何约束。一个 Run 理论上可以尝试做很多事，然后全部失败。

**判断**：C2 基本可用。任务级别的拆分是好的，但缺少单个 Run 内部的进展控制。

#### C3：质量是否被独立验证

**当前状态**：Gate 系统执行 shell 命令作为质量检查（[gates.py](src/agentflow/services/gates.py)）：

```python
class GateEvaluator:
    def evaluate(self, commands: list[str]) -> GateResult:
        # 逐个执行 shell 命令，返回通过/失败
```

这是**静态命令检查**——lint 通过、test 通过就算通过。

**差距**：

| 验证层次 | 当前支持 | 三篇文章的对应 |
|---------|---------|--------------|
| 编译/语法检查 | Gate 命令 | OpenAI 的自定义 linter |
| 单元测试 | Gate 命令 | Anthropic 的单元测试 |
| 端到端功能验证 | 不支持 | Anthropic 的 Evaluator 用 Playwright 做真实用户级操作 |
| 架构一致性 | 不支持 | OpenAI 的结构性 linter（依赖方向、层级约束） |
| 人类意图满足度 | 不支持 | Anthropic 的 sprint contract 对照验收 |

**核心问题**：Gate 只能验证"代码是否正确"，不能验证"功能是否可用"。Anthropic 文章中举了一个具体例子——Evaluator 发现 FastAPI 路由顺序导致 `reorder` 被当作 `frame_id`，返回 422。这种 bug lint 不会发现，只有端到端测试才能捕获。

**判断**：C3 不足。质量验证停留在静态检查层面，缺少功能级和意图级的验证。

#### C4：Session 之间的交接

**当前状态**：Ledger 的 `feedback` 事件族包含 `handoff.recorded` 类型（[ledger.py:33](src/agentflow/services/ledger.py#L33)），但：

1. 它是**可选的**——没有代码强制写入
2. 它是**非结构化的**——`evidence_json` 里放什么都行
3. Runner 完成任务时直接 finalize run，**不要求 Agent 留下交接信息**（[runner.py:254-313](src/agentflow/services/runner.py#L254-L313)）
4. 下一个 Agent 接手时，通过 `previous_runs` 获得历史，但只有 `status` 和 `result_summary`，没有结构化的进展描述

对比 Anthropic 的交接协议：
- **强制的**：每个 session 结束必须更新 progress file + git commit
- **结构化的**：JSON 格式，包含"做了什么、还剩什么、阻塞在哪"
- **可恢复的**：下一个 session 开始时先读 progress file、读 git log、启动 dev server 验证

**判断**：C4 严重不足。Agent 之间没有结构化的交接机制，下一个 Agent 接手时基本从零开始。

#### C5：持续修正

**当前状态**：
- Gate profile 可以配置质量检查命令
- Ledger 记录了所有事件，可以事后审计
- Console 展示了审计时间线

**差距**：
- 没有类似 OpenAI 的"golden principles"——将项目规范编码为可执行的规则
- 没有"doc gardening"机制——定期扫描并修复代码质量偏差
- 没有质量评分系统——无法判断项目在变好还是变差
- 人类的反馈（review comments、bug reports）没有被系统性地捕获和编码

**判断**：C5 部分不足。有审计能力，但缺少持续修正的机制。

### 2.3 检视总结

| 核心问题 | 状态 | 关键差距 |
|---------|------|---------|
| C1 上下文 | 不足 | 缺少项目规则、历史决策、交接信息、验收标准 |
| C2 拆分 | 基本可用 | 任务级拆分好，Run 内部缺粒度控制 |
| C3 独立验证 | 不足 | 只有静态命令检查，缺功能级和意图级验证 |
| C4 交接 | 严重不足 | 没有结构化的交接协议 |
| C5 持续修正 | 部分不足 | 有审计，缺持续修正机制 |

---

## 第三部分：AgentFlow 是什么类型的 Harness

### 3.1 错误的二分法

之前的分析中我创造了一个"执行 harness vs 编排 harness"的二分法。但三篇文章清楚地表明，harness 并不按"单任务 vs 多任务"来区分——OpenAI 管了 1500+ PRs，Anthropic 的 feature list 有 200+ 项。

正确的看法是：**harness 是一套组件的集合，不同的 harness 在这五个核心问题上有不同的强弱组合。**

### 3.2 AgentFlow 和 Anthropic/OpenAI Harness 的关系

```
                    C1       C2       C3       C4       C5
                 上下文    拆分     验证      交接     修正
Anthropic #1    ██████   ████░░   ███░░░   ██████   ██░░░░
Anthropic #2    ██████   ██████   ██████   ██████   ████░░
OpenAI          ██████   ██████   ██████   ██████   ██████
AgentFlow       ██░░░░   ██████   ██░░░░   █░░░░░   ███░░░
```

AgentFlow 的强项在 C2（任务拆分和调度），弱项在 C1（上下文）、C3（验证）、C4（交接）。

但这不意味着 AgentFlow 是一个"不完整的 harness"而应该去补齐所有短板。更准确的定位是：

> **AgentFlow 在 C2 上做得比三篇文章都强（多 Agent 协调、lease 管理、状态机），但在 C1/C3/C4 上需要和执行侧的 harness 协作。**

Anthropic 的 harness 运行在 Claude Agent SDK 内部，直接管理 Agent 的 prompt 和 session。OpenAI 的 harness 嵌入在代码仓库中，Agent 可以直接读取。这两种 harness 对 Agent 的控制是**直接的**。

AgentFlow 对 Agent 的控制是**间接的**——通过 Adapter 接口。Agent 不在 AgentFlow 内部运行，而是在外部（OpenClaw、Codex CLI、Claude Code）运行。AgentFlow 管理的是**任务的调度和追踪**，不是 Agent 的执行过程。

这意味着：
- C1（上下文）的丰富化需要**通过 Adapter 接口传递更多结构化信息给 Agent**
- C3（验证）的增强需要**在 Runner 流程中增加 Evaluator 步骤**
- C4（交接）的实现需要**在 Store 中增加结构化的交接数据模型**
- C5（修正）需要**将人类的反馈编码回系统**

### 3.3 AgentFlow 的真正定位

AgentFlow 不是一个"还在补课的 harness"。它在多 Agent 编排方面（C2）有独特的价值——三篇文章中没有一个处理多个不同类型 Agent 的协调问题。OpenAI 只用 Codex，Anthropic 只用 Claude。

AgentFlow 的定位是：

> **一个专注任务调度和追踪的 harness，通过 Adapter 接口与执行侧 harness 协作，让多个异构 Agent 能够在统一的治理模型下工作。**

它不需要复制 Anthropic 的 progress file 或 OpenAI 的 docs/ 知识库。它需要做的是：**定义标准化的接口，让执行侧 harness 能够将上下文、交接信息、验收结果结构化地输入到 AgentFlow 中。**

---

## 第四部分：基于 Harness 工程的具体改进建议

### 4.1 结构化 Handoff Protocol（解决 C4）

**问题**：Agent 执行完毕后不留结构化信息，下一个 Agent 接手时只能看到 run 的 status 和 result_summary。

**建议**：

在 schema 中增加 `handoff_artifacts` 表：

```sql
CREATE TABLE IF NOT EXISTS handoff_artifacts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id INTEGER NOT NULL REFERENCES tasks(id),
    run_id INTEGER NOT NULL REFERENCES runs(id),
    project TEXT NOT NULL,
    agent_name TEXT NOT NULL,
    content JSON NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY(task_id) REFERENCES tasks(id) ON DELETE CASCADE,
    FOREIGN KEY(run_id) REFERENCES runs(id) ON DELETE CASCADE
);
```

`content` 的结构（学习 Anthropic 的 progress file）：

```json
{
  "what_was_done": "实现了 auth middleware，本地测试通过",
  "what_remains": "需要与真实 OAuth provider 集成测试，token refresh 错误处理",
  "blockers": ["需要 DevOps 提供 OAuth client credentials"],
  "files_changed": ["src/auth/middleware.py", "tests/test_auth.py"],
  "next_steps": ["运行集成测试", "添加 token refresh 错误路径"],
  "confidence": "high",
  "dev_server_ok": true
}
```

在 `AdapterContext` 中增加 `previous_handoff`：

```python
@dataclass
class AdapterContext:
    task: Task
    project: str
    repo_full_name: str | None
    previous_runs: list[dict[str, object]]
    gate_profile: dict[str, object] | None
    previous_handoff: dict | None  # 新增：前序 Agent 的交接信息
```

在 `AgentAdapter` 接口中增加可选的 `write_handoff` 方法：

```python
class AgentAdapter(Protocol):
    name: str
    def execute(self, context: AdapterContext, agent_name: str) -> AdapterResult: ...
    def write_handoff(self, context: AdapterContext, result: AdapterResult) -> dict | None:
        """可选：Agent 执行后生成交接信息。默认返回 None。"""
```

**为什么这是 Adapter 接口而不是 Runner 强制**：因为 Agent 内部的执行细节（"做了什么、还剩什么"）只有 Agent 自己知道。AgentFlow 不应该定义 Agent 如何生成这些信息，而是定义**存储和检索的格式**。执行侧 harness（如 OpenClaw）负责在 Agent 执行完成后提取交接信息并回传。

### 4.2 Acceptance Criteria（解决 C1 和 C3 的一部分）

**问题**：Task 只有 `title` 和 `description`，Agent 不清楚"完成"意味着什么。

**建议**：

在 `tasks` 表增加 `acceptance_criteria` 列：

```sql
ALTER TABLE tasks ADD COLUMN acceptance_criteria TEXT;
-- 存储为 JSON 数组
```

格式学习 Anthropic 的 `feature_list.json`，但更轻量：

```json
[
  {
    "id": "ac-1",
    "description": "用户可以通过 GitHub OAuth 登录",
    "required": true,
    "status": "pending"
  },
  {
    "id": "ac-2",
    "description": "OAuth 失败时显示错误提示",
    "required": false,
    "status": "pending"
  }
]
```

**关键约束**（从 Anthropic 学到的）：
- `acceptance_criteria` 的**创建者**是人类或 Planner Agent
- 执行 Agent **只能修改 `status` 字段**，不能修改 `description` 或删除 criteria
- 这个约束在 Store 层强制执行，不依赖 Agent 自律

在 `AdapterContext` 中传递 acceptance criteria：

```python
@dataclass
class AdapterContext:
    # ...existing...
    acceptance_criteria: list[dict] | None  # 新增
```

在 OpenClaw adapter 的 prompt 中明确告知 Agent：

```
验收标准：
1. [ac-1] 用户可以通过 GitHub OAuth 登录 (required)
2. [ac-2] OAuth 失败时显示错误提示 (optional)

你只能将每个标准的 status 标记为 passed 或 failed，不能修改或删除标准。
```

**价值**：
- 解决 C1 的一部分——Agent 知道"完成"意味着什么
- 解决 C3 的一部分——Gate 可以检查 acceptance criteria 的完成率
- 解决 Anthropic 文章中的"过早宣布完成"问题

### 4.3 Project Principles（解决 C1 和 C5）

**问题**：Agent 不知道项目的架构约束和编码规范。

**建议**：

在 `gate_profiles` 表旁边增加 `project_principles`（或直接扩展 `gate_profiles`）：

```sql
ALTER TABLE gate_profiles ADD COLUMN principles TEXT;
-- 存储为 JSON 数组
```

```json
[
  {
    "id": "p-1",
    "rule": "所有 API 入口必须在 boundary 层验证输入格式",
    "enforcement": "linter",
    "severity": "error"
  },
  {
    "id": "p-2",
    "rule": "优先使用共享工具包而非手写 helper",
    "enforcement": "review",
    "severity": "warning"
  },
  {
    "id": "p-3",
    "rule": "不要猜测数据格式——必须验证或使用 typed SDK",
    "enforcement": "linter",
    "severity": "error"
  }
]
```

这些原则学习 OpenAI 的 "golden principles"——将项目的编码规范从人类脑中提取出来，变成 Agent 可读、可执行的规则。

在 `AdapterContext` 中传递：

```python
@dataclass
class AdapterContext:
    # ...existing...
    project_principles: list[dict] | None  # 新增
```

**价值**：
- 解决 C1——Agent 知道项目的边界规则
- 解决 C5——原则可以被 linter 或 review 强制执行，形成持续修正

### 4.4 Evaluator 步骤（解决 C3）

**问题**：Gate 只能做静态命令检查，不能验证功能是否真正可用。

**建议**：

不实现完整的 Evaluator Agent（成本太高），而是在 Runner 流程中增加**可选的 evaluator 步骤**：

```python
# runner.py 的 execute_prepared_run 中，gate 之后

if result.success and gate_passed and self._has_evaluator(project):
    eval_result = self._run_evaluator_step(project, task, run_id, prepared_run)
    # evaluator 的反馈写入 Ledger，不直接 block
    # 而是在 Console 中展示，由人类决定
```

Evaluator 的实现可以有两种形式：

**方案 A：调用独立的 Evaluator Agent**

```python
def _run_evaluator_step(self, project, task, run_id, prepared_run):
    evaluator = self.registry.get("evaluator")  # 专门的 evaluator adapter
    context = AdapterContext(task=task, ...)
    return evaluator.execute(context, "evaluator-agent")
```

**方案 B：基于 Acceptance Criteria 的自动化检查**

```python
def _run_evaluator_step(self, project, task, run_id, prepared_run):
    # 检查 acceptance criteria 的完成状态
    criteria = self.store.get_acceptance_criteria(task.id)
    unchecked = [c for c in criteria if c["required"] and c["status"] != "passed"]
    if unchecked:
        return EvalResult(passed=False, feedback=f"未完成的必要标准: {unchecked}")
    return EvalResult(passed=True, feedback="所有必要标准已通过")
```

方案 B 更实际——它不依赖额外的 Agent，而是利用 acceptance criteria 做结构化检查。

在 Ledger 中增加 `evaluation.*` 事件类型（新增 event family 或在现有 family 下增加 type）：

```python
"execution": (
    # ...existing...
    "evaluation.started",
    "evaluation.completed",
)
```

**价值**：
- 解决 C3——从纯静态检查扩展到结构化的功能验证
- 学习 Anthropic 的 generator-evaluator 分离思想，但以更轻量的方式实现
- 评估结果写入 Ledger，形成审计链

### 4.5 Harness 强度可配置（解决演化问题）

**问题**：每个组件加上去就永远在，无法随模型能力进化而简化。

**建议**：

在项目配置中为每个 harness 组件设置强度级别：

```yaml
# agentflow.yaml（或 gate_profiles 的扩展）
harness:
  handoff: required       # required | optional | off
  acceptance_criteria: strict  # strict | lenient | off
  evaluator: enabled      # enabled | disabled
  gate: strict            # strict | relaxed | off
  context_enrichment: full    # full | minimal | off
  principles: included    # included | excluded
```

**设计理由**（学习 Anthropic 第三篇文章）：
- Opus 4.5 需要 sprint 拆分和 context reset，4.6 不需要
- 同理，不同项目、不同 Agent、不同任务类型可能需要不同强度的 harness
- 简单的 bugfix 不需要 acceptance criteria 和 evaluator
- 关键的功能开发需要严格的验收标准

这个配置可以在 `gate_profiles` 表中存储，也可以用单独的配置文件。关键是要让 harness 的强度**可调**而非**固定**。

---

## 第五部分：改进优先级与路线图调整

### 5.1 优先级判断

| 改进项 | 解决的核心问题 | 实现成本 | 价值 |
|--------|-------------|---------|------|
| Handoff Protocol | C4 交接 | 中（新表 + AdapterContext 扩展） | 高——没有交接就没有连续性 |
| Acceptance Criteria | C1+C3 上下文+验证 | 中（新列 + Store 方法） | 高——没有标准就无法判断完成 |
| Project Principles | C1+C5 上下文+修正 | 低（扩展 gate_profiles） | 中——Agent 需要知道规则 |
| Evaluator 步骤 | C3 独立验证 | 高（需要新的 Adapter 或逻辑） | 中——但依赖 Acceptance Criteria |
| Harness 强度配置 | 演化 | 低（配置扩展） | 中——让 harness 可演化 |

### 5.2 与现有路线图的关系

当前路线图（[productionization-roadmap.md](docs/2026-04-01-productionization-roadmap.md)）的 P0 聚焦于"把 Agent 工作过程呈现出来"，这和 Harness 工程的洞察是**一致但互补**的：

- 现有 P0-1（统一事件模型）→ 和 C4（交接）直接相关
- 现有 P0-2（Evidence-first 控制台）→ 需要 C1（上下文）的丰富化才能展示有意义的证据
- 现有 P0-3（人工接管闭环）→ 和 C5（持续修正）相关
- 现有 P0-4（证据优先的状态推进）→ 和 C3（验证）相关

**建议调整**：在 P0 阶段同时推进 Handoff Protocol 和 Acceptance Criteria 的数据模型设计。这不影响现有的可视化工作，但确保 Console 有更丰富的数据可以展示。

### 5.3 建议的执行顺序

```
Phase 1（当前 sprint）：
  ├── Handoff Protocol 数据模型 + Store 方法
  ├── Acceptance Criteria 列 + Store 方法
  └── 这两个为 P0 的可视化提供了更丰富的数据源

Phase 2（P0 完成后）：
  ├── Project Principles（扩展 gate_profiles）
  ├── Harness 强度配置
  └── AdapterContext 丰富化（传递 principles + criteria + handoff）

Phase 3（P1 阶段）：
  ├── Evaluator 步骤（轻量版：基于 criteria 的检查）
  └── 与生产化路线图的 P1 同步推进
```

---

## 第六部分：总结

### 核心结论

1. **Harness 是具体的管理 Agent 工作行为的组件集合**，不是抽象概念。三篇文章中的每个 harness 组件都是可以读、可以改、可以运行的代码和数据结构。

2. **AgentFlow 本身就是一种 harness**——它在任务调度和追踪（C2）上有独特价值（多 Agent 协调、lease 管理、状态机），但在上下文（C1）、验证（C3）、交接（C4）上需要补强。

3. **AgentFlow 不需要复制执行侧 harness 的做法**。Anthropic 的 progress file 运行在 Agent SDK 内部，OpenAI 的 docs/ 知识库嵌入在仓库中。AgentFlow 应该**定义标准化的接口**，让执行侧 harness 能够将上下文、交接、验收结果结构化地输入到系统中。

4. **最紧迫的差距是 C4（交接）**——没有结构化的交接协议，Agent 之间的连续性就完全依赖每个 Agent 自己的理解能力。这是 Anthropic 两篇文章的核心发现，也是 AgentFlow 当前最薄弱的环节。

5. **第二紧迫的是验收标准**——没有明确的"完成"定义，Agent 要么过早宣布完成（Anthropic 文章中的失败模式），要么永远不知道做到什么程度才算好。

6. **Harness 应该可演化**——随着模型能力提升，某些组件可以简化或关闭。设计时就要考虑强度可配置，而不是永远运行全部检查。

### 一句话总结

> AgentFlow 的改进方向不是"成为更好的 harness"，而是在保持任务调度优势的前提下，通过标准化的接口补强上下文传递、质量验证、和 session 交接这三个薄弱环节，让多个异构 Agent 能在统一的治理模型下持续高效地工作。
