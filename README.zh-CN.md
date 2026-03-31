# AgentFlow（中文）

面向多种 Coding Agent 的轻量级、阶段（Stage）优先任务控制插件。它帮助你在一个或多个仓库中完成任务发现、流转管理、执行落地、PR/Issue 关联与状态审计。

语言：中文 | [English](./README.md)

## 项目定位

AgentFlow 不是新的“大而全”Agent 平台，而是一个可插拔的控制层（control plugin）：

- 发现问题：从 GitHub issue / webhook / 定时任务进入任务池
- 管理流程：以 stage 为主视图，status 为内部精细状态
- 驱动执行：触发 agent 运行、记录 run/run steps
- 维护闭环：PR/Issue 链接、状态回写、审计追踪

## 我们的优势

- 轻量：SQLite 本地优先，几乎零基础设施依赖
- 插件优先：OpenClaw 原生插件 + 其他 agent bundle 模板
- 可读性强：Stage Board 统一流程视图
- 过程可控：状态迁移校验 + gate 门禁 + 人工强制（带审计）
- 全链路追踪：runs / triggers / status_history / audit
- 支持多仓库：一个控制面管理多个项目仓库

## 快速开始

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .

agentflow init --db ./data/agentflow.db
agentflow create-project kthena --repo volcano-sh/kthena
agentflow add-task --project kthena --title "controller partition revision bug" --priority 5 --impact 5 --effort 2 --source github --external-id 841
agentflow serve --db ./data/agentflow.db --host 127.0.0.1 --port 8787
```

打开：`http://127.0.0.1:8787`

## Web 控制台能力

- Stage Board（支持拖拽切换阶段）
- 任务筛选（stage/source）
- 任务详情（PR 详情、相关链接、运行摘要）
- 手动状态流转（支持 note 与 force）
- 审计面板（状态变化全记录）
- 运行流面板（Recent Runs）

## Webhook 与 API

### Webhook

- `POST /webhook/github/comment?project=<project>&adapter=mock&agent=bot`
- `POST /webhook/github/issues?project=<project>`
- `POST /webhook/github?project=<project>&adapter=mock&agent=bot`

可选签名校验：`X-Hub-Signature-256`

### 控制台 API

- `GET /api/flow?project=<project>`
- `POST /api/task/<id>/move`
- `GET /api/audit?project=<project>&limit=30`
- `POST /api/task/<id>/run`

## OpenClaw 原生插件

插件目录：`plugins/openclaw-agentflow/`

本地安装：

```bash
openclaw plugins install ./plugins/openclaw-agentflow
openclaw plugins enable agentflow
openclaw gateway restart
```

已暴露能力：

- Command: `agentflow.run`
- Command: `agentflow.help`
- Tool: `agentflow_status`
- Tool: `agentflow_capabilities`
- Route: `GET /agentflow/capabilities`
- Route: `POST /agentflow/webhook/comment`
- Route: `POST /agentflow/webhook/issues`
- Route: `POST /agentflow/webhook/github`

## 测试

```bash
cd /home/shawn/github/agentflow
PYTHONPATH=src python3 -m unittest discover -s tests -p 'test_*.py' -v
```

---

English version: [README.md](./README.md)
