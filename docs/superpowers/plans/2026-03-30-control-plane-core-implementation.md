# Control Plane Core Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement AgentFlow control-plane core so task execution is auditable, lease-safe, and gate-enforced for GitHub-triggered multi-round task updates.

**Architecture:** Extend the current SQLite-backed control plane with run-ledger tables (`runs`, `run_steps`, `triggers`, `gate_profiles`) and service APIs that enforce state transitions and idempotent execution records. Keep adapter execution pluggable while making every automated action traceable from trigger to gate result.

**Tech Stack:** Python 3, SQLite, argparse CLI, unittest

---

### Task 1: Run Ledger Data Model

**Files:**
- Modify: `src/agentflow/schema.py`
- Modify: `src/agentflow/store.py`
- Test: `tests/test_store.py`

- [ ] **Step 1: Write failing tests for run lifecycle APIs**

Add tests for creating a run, appending steps, and finalizing run status.

- [ ] **Step 2: Run tests and verify failure**

Run: `cd /home/shawn/github/agentflow && PYTHONPATH=src python3 -m unittest discover -s tests -p 'test_*.py' -v`
Expected: FAIL on missing run ledger methods/tables.

- [ ] **Step 3: Add schema tables for run ledger**

Implement tables: `runs`, `run_steps`, `triggers`, `gate_profiles` and indexes.

- [ ] **Step 4: Implement store methods**

Add methods: `create_run`, `append_run_step`, `finalize_run`, `list_runs`, `list_run_steps`, `upsert_trigger`.

- [ ] **Step 5: Run tests to pass**

Run the unittest command above.
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/agentflow/schema.py src/agentflow/store.py tests/test_store.py
git commit -m "feat: add run ledger tables and store APIs"
```

### Task 2: Gate Profile Core

**Files:**
- Modify: `src/agentflow/store.py`
- Create: `src/agentflow/services/gates.py`
- Test: `tests/test_gates.py`

- [ ] **Step 1: Write failing tests for gate profile read/write and evaluation**
- [ ] **Step 2: Run tests and confirm failure**
- [ ] **Step 3: Implement gate profile persistence and parser**
- [ ] **Step 4: Implement gate evaluator result model**
- [ ] **Step 5: Run tests to pass**
- [ ] **Step 6: Commit**

```bash
git add src/agentflow/store.py src/agentflow/services/gates.py tests/test_gates.py
git commit -m "feat: add gate profile persistence and evaluator"
```

### Task 3: Trigger Idempotency and Event Recording

**Files:**
- Modify: `src/agentflow/store.py`
- Create: `src/agentflow/services/triggers.py`
- Test: `tests/test_triggers.py`

- [ ] **Step 1: Write failing idempotency tests**
- [ ] **Step 2: Run tests and confirm failure**
- [ ] **Step 3: Implement idempotency key check + trigger upsert**
- [ ] **Step 4: Implement trigger-to-run linking helpers**
- [ ] **Step 5: Run tests to pass**
- [ ] **Step 6: Commit**

```bash
git add src/agentflow/store.py src/agentflow/services/triggers.py tests/test_triggers.py
git commit -m "feat: add trigger idempotency and event recording"
```

### Task 4: Runner Integration with Run Ledger and Gates

**Files:**
- Modify: `src/agentflow/services/runner.py`
- Modify: `src/agentflow/adapters/base.py`
- Modify: `tests/test_runner.py`

- [ ] **Step 1: Write failing tests for run steps + gate result wiring**
- [ ] **Step 2: Run tests and confirm failure**
- [ ] **Step 3: Update runner to create run record before execution**
- [ ] **Step 4: Append run steps throughout execution lifecycle**
- [ ] **Step 5: Enforce gate result before status advance to pr_ready/pr_open**
- [ ] **Step 6: Run tests to pass**
- [ ] **Step 7: Commit**

```bash
git add src/agentflow/services/runner.py src/agentflow/adapters/base.py tests/test_runner.py
git commit -m "feat: wire runner with run ledger and gate enforcement"
```

### Task 5: CLI Ops for Run Inspection

**Files:**
- Modify: `src/agentflow/cli.py`
- Test: `tests/test_cli_smoke.py`
- Modify: `README.md`

- [ ] **Step 1: Write failing CLI smoke tests for run inspection commands**
- [ ] **Step 2: Run tests and confirm failure**
- [ ] **Step 3: Add commands: `runs`, `run-steps`, `triggers`, `gate-profile`**
- [ ] **Step 4: Update README with new ops workflow**
- [ ] **Step 5: Run tests to pass**
- [ ] **Step 6: Commit**

```bash
git add src/agentflow/cli.py tests/test_cli_smoke.py README.md
git commit -m "feat: add run inspection and gate profile CLI commands"
```

### Task 6: Integration Verification and Documentation Sync

**Files:**
- Modify: `docs/superpowers/specs/2026-03-30-control-plane-core-design.md`
- Modify: `docs/superpowers/specs/2026-03-30-control-plane-presentation-design.md`

- [ ] **Step 1: Execute end-to-end verification script**

Run:
`cd /home/shawn/github/agentflow && PYTHONPATH=src python3 -m unittest discover -s tests -p 'test_*.py' -v`

Expected: All tests pass.

- [ ] **Step 2: Validate manual smoke flow**

Run:
- `agentflow --db ./data/agentflow.db init`
- `agentflow --db ./data/agentflow.db create-project demo --repo example/demo`
- `agentflow --db ./data/agentflow.db add-task --project demo --title "demo fix" --priority 5 --impact 5 --effort 2`
- `agentflow --db ./data/agentflow.db run-once --project demo --adapter mock --agent codex-a`

Expected: run and task status updates are visible and auditable.

- [ ] **Step 3: Document implemented vs planned status**
- [ ] **Step 4: Commit**

```bash
git add docs/superpowers/specs/2026-03-30-control-plane-core-design.md docs/superpowers/specs/2026-03-30-control-plane-presentation-design.md
git commit -m "docs: sync control-plane specs with implementation status"
```

## Execution Mode

Inline execution selected: implement tasks in this session with checkpoints after each task.
