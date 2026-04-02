# Event Model v1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement the `ledger_events`-centered event model so AgentFlow records, streams, audits, and displays one unified domain event contract while keeping `tasks` and `runs` as current-state snapshots.

**Architecture:** Add a new `ledger_events` table plus store/service APIs for writing and querying domain events, then migrate write paths in runner/webhook/manual task actions so events are created before snapshot updates. Finally, switch CLI, API, SSE, and console rendering to consume unified ledger events and derived summaries instead of stitching together `events`, `status_history`, and `run_steps`.

**Tech Stack:** Python 3, SQLite, argparse CLI, unittest, browser JS

---

## File Structure

**New files:**

- `src/agentflow/services/ledger.py`: event creation helpers, event-family/type constants, derived summary helpers
- `tests/test_ledger.py`: unit tests for ledger event writing, querying, and projection helpers

**Modified files:**

- `src/agentflow/schema.py`: add `ledger_events` schema and indexes
- `src/agentflow/store.py`: add ledger persistence/query APIs and compatibility helpers
- `src/agentflow/services/runner.py`: emit unified ledger events for claim/run/step/gate/status changes
- `src/agentflow/services/triggers.py`: expose trigger IDs cleanly for ledger linkage when needed
- `src/agentflow/services/webhook.py`: emit comment/duplicate/queued/run-trigger events
- `src/agentflow/console.py`: switch `/api/events`, `/api/audit`, `/api/task/<id>` to ledger-backed responses
- `src/agentflow/web/static/console.js`: render unified timeline/audit/event stream payloads
- `src/agentflow/cli.py`: switch `audit` and `run-steps` style inspection to ledger-backed commands/output
- `tests/test_store.py`: schema/store coverage for `ledger_events`
- `tests/test_runner.py`: verify runner writes expected ledger events
- `tests/test_webhook.py`: verify webhook writes comment/duplicate/run-trigger events
- `tests/test_console_api.py`: verify API/SSE returns unified event objects
- `tests/test_console_flow.py`: verify broker/task detail flow uses ledger events
- `tests/test_cli_smoke.py`: verify CLI inspection commands use new event model
- `README.md`: document unified event model and updated API semantics
- `README.zh-CN.md`: same as above in Chinese

### Task 1: Add Ledger Event Schema and Store APIs

**Files:**
- Modify: `src/agentflow/schema.py`
- Modify: `src/agentflow/store.py`
- Test: `tests/test_store.py`

- [ ] **Step 1: Write the failing schema/store tests**

Add tests in `tests/test_store.py` for:

```python
def test_append_ledger_event_and_list_task_timeline(self) -> None:
    task_id = self.store.add_task(
        project="demo",
        title="ledger-event-test",
        description=None,
        priority=3,
        impact=3,
        effort=3,
        source="manual",
        external_id=None,
    )
    run_id = self.store.create_run(
        task_id=task_id,
        project="demo",
        trigger_type="manual",
        trigger_ref="cli:test",
        adapter="mock",
        agent_name="codex-a",
        idempotency_key="ledger-event-test-run",
    )
    event_id = self.store.append_ledger_event(
        project="demo",
        task_id=task_id,
        run_id=run_id,
        trigger_id=None,
        parent_event_id=None,
        event_family="execution",
        event_type="run.started",
        actor_type="agent",
        actor_id="codex-a",
        source_type="manual",
        source_ref="cli:test",
        status_from="ready",
        status_to="in_progress",
        run_status_from=None,
        run_status_to="running",
        severity="info",
        summary="Run started for task #1",
        evidence={"step_name": "claim"},
        next_action={"recommended": "observe"},
        context={"adapter": "mock"},
        idempotency_key="ledger-event-test-event",
    )
    rows = self.store.list_task_timeline(task_id, limit=10)
    self.assertEqual(event_id, int(rows[0]["id"]))
    self.assertEqual("run.started", rows[0]["event_type"])
```

- [ ] **Step 2: Run the store tests to verify failure**

Run:
`cd "$(git rev-parse --show-toplevel)" && PYTHONPATH=src python3 -m unittest tests.test_store -v`

Expected: FAIL on missing `ledger_events` table and missing store methods such as `append_ledger_event`.

- [ ] **Step 3: Add the `ledger_events` table and indexes**

Update `src/agentflow/schema.py` with SQL matching the spec:

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
    recorded_at TEXT NOT NULL DEFAULT (datetime('now'))
);
```

- [ ] **Step 4: Implement store persistence/query methods**

Add these methods to `src/agentflow/store.py`:

```python
def append_ledger_event(...)-> int: ...
def list_project_events(self, project: str, after_id: int = 0, limit: int = 200) -> list[sqlite3.Row]: ...
def list_task_timeline(self, task_id: int, limit: int = 50) -> list[sqlite3.Row]: ...
def list_run_timeline(self, run_id: int, limit: int = 100) -> list[sqlite3.Row]: ...
def list_project_audit_events(self, project: str, limit: int = 50) -> list[sqlite3.Row]: ...
```

Serialize `evidence`, `next_action`, and `context` with `json.dumps(..., ensure_ascii=False)` and deserialize them in one place for read helpers.

- [ ] **Step 5: Run the store tests to verify pass**

Run:
`cd "$(git rev-parse --show-toplevel)" && PYTHONPATH=src python3 -m unittest tests.test_store -v`

Expected: PASS with new ledger schema and query helpers.

- [ ] **Step 6: Commit**

```bash
git add src/agentflow/schema.py src/agentflow/store.py tests/test_store.py
git commit -m "feat: add ledger event schema and store APIs"
```

### Task 2: Add Ledger Service and Derived Summary Helpers

**Files:**
- Create: `src/agentflow/services/ledger.py`
- Test: `tests/test_ledger.py`

- [ ] **Step 1: Write the failing ledger service tests**

Create `tests/test_ledger.py` covering:

```python
def test_build_gate_failed_event_payload() -> None:
    event = build_gate_failed_event(
        task_id=12,
        run_id=33,
        actor_id="gate-evaluator",
        summary="Gate failed on pytest -q",
        error_code="gate_failed",
        log_excerpt="2 tests failed",
    )
    assert event["event_family"] == "risk"
    assert event["event_type"] == "gate.failed"
    assert event["severity"] == "error"
    assert event["evidence"]["error_code"] == "gate_failed"


def test_derive_task_summary_prefers_recent_risk_event() -> None:
    summary = derive_task_summary([
        {"event_type": "progress.reported", "summary": "editing files", "severity": "info"},
        {"event_type": "gate.failed", "summary": "pytest failed", "severity": "error"},
    ])
    assert summary["latest_risk"]["event_type"] == "gate.failed"
```

- [ ] **Step 2: Run the new ledger tests to verify failure**

Run:
`cd "$(git rev-parse --show-toplevel)" && PYTHONPATH=src python3 -m unittest tests.test_ledger -v`

Expected: FAIL because `src/agentflow/services/ledger.py` does not exist.

- [ ] **Step 3: Implement the ledger service**

Create `src/agentflow/services/ledger.py` with:

```python
EVENT_FAMILIES = {"dispatch", "execution", "governance", "feedback", "risk"}

def build_event(...)-> dict[str, object]:
    return {
        "event_family": event_family,
        "event_type": event_type,
        "actor_type": actor_type,
        "actor_id": actor_id,
        "summary": summary,
        "severity": severity,
        "evidence": evidence or {},
        "next_action": next_action or {},
        "context": context or {},
    }

def derive_task_summary(events: list[dict[str, object]]) -> dict[str, object]:
    ...
```

Keep it focused on:

- building normalized event payload dictionaries
- validating family/type/severity basics
- deriving task summary fields for API/UI (`latest_progress`, `latest_handoff`, `latest_risk`, `recommended_actions`)

- [ ] **Step 4: Run the ledger tests to verify pass**

Run:
`cd "$(git rev-parse --show-toplevel)" && PYTHONPATH=src python3 -m unittest tests.test_ledger -v`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/agentflow/services/ledger.py tests/test_ledger.py
git commit -m "feat: add ledger event builders and summary helpers"
```

### Task 3: Migrate Runner Write Paths to Ledger Events

**Files:**
- Modify: `src/agentflow/services/runner.py`
- Modify: `src/agentflow/store.py`
- Modify: `tests/test_runner.py`

- [ ] **Step 1: Write the failing runner tests**

Extend `tests/test_runner.py` to assert that a successful run writes events in order:

```python
timeline = self.store.list_task_timeline(task.id, limit=20)
event_types = [row["event_type"] for row in timeline]
self.assertIn("task.claimed", event_types)
self.assertIn("run.started", event_types)
self.assertIn("step.passed", event_types)
self.assertIn("gate.passed", event_types)
self.assertIn("task.status_changed", event_types)
```

Also add a gate-failure case asserting:

```python
self.assertIn("gate.failed", event_types)
self.assertIn("task.blocked", event_types)
```

- [ ] **Step 2: Run the runner tests to verify failure**

Run:
`cd "$(git rev-parse --show-toplevel)" && PYTHONPATH=src python3 -m unittest tests.test_runner -v`

Expected: FAIL because runner only writes `run_steps` and task status snapshots.

- [ ] **Step 3: Implement ledger writes in runner**

Update `src/agentflow/services/runner.py` so it:

- writes `task.claimed` immediately after claim succeeds
- writes `run.started` immediately after `create_run`
- writes `step.started` / `step.passed` / `step.failed` around adapter execution
- writes `gate.passed` / `gate.failed`
- writes `task.status_changed` for `review` or `blocked`

Keep `runs` as snapshot state and continue updating it, but treat ledger events as the primary record.

- [ ] **Step 4: Add compatibility writes only where still needed**

If `run_steps` are temporarily preserved, write them from the same points as a compatibility projection. Do not create new runner behavior that bypasses `ledger_events`.

- [ ] **Step 5: Run the runner tests to verify pass**

Run:
`cd "$(git rev-parse --show-toplevel)" && PYTHONPATH=src python3 -m unittest tests.test_runner -v`

Expected: PASS with ledger events present for both success and failure runs.

- [ ] **Step 6: Commit**

```bash
git add src/agentflow/services/runner.py src/agentflow/store.py tests/test_runner.py
git commit -m "feat: emit unified ledger events from runner"
```

### Task 4: Migrate Webhook and Manual Governance Actions

**Files:**
- Modify: `src/agentflow/services/webhook.py`
- Modify: `src/agentflow/store.py`
- Modify: `src/agentflow/console.py`
- Modify: `tests/test_webhook.py`
- Modify: `tests/test_console_api.py`

- [ ] **Step 1: Write failing tests for webhook/manual event emission**

Add tests asserting:

- PR comment ingestion writes `comment.received`
- duplicate comment handling writes a duplicate/ignored governance or feedback event
- manual move writes `task.force_moved` when `force=True`
- progress endpoint writes `progress.reported`

Example assertion:

```python
timeline = self.store.list_task_timeline(task_id, limit=20)
self.assertEqual("comment.received", timeline[0]["event_type"])
```

- [ ] **Step 2: Run webhook and console API tests to verify failure**

Run:
`cd "$(git rev-parse --show-toplevel)" && PYTHONPATH=src python3 -m unittest tests.test_webhook tests.test_console_api -v`

Expected: FAIL because webhook/manual endpoints do not yet emit ledger events.

- [ ] **Step 3: Implement event writes for webhook and manual actions**

Update:

- `src/agentflow/services/webhook.py` to emit `comment.received`, duplicate-ignore, and queued/run-trigger events
- `src/agentflow/store.py` or call sites so `move_task`, `claim_next_task`, `claim_task`, `heartbeat`, and `release_claim` can attach event metadata
- `src/agentflow/console.py` progress/move handlers to write `progress.reported` and `task.force_moved`

- [ ] **Step 4: Run webhook and console API tests to verify pass**

Run:
`cd "$(git rev-parse --show-toplevel)" && PYTHONPATH=src python3 -m unittest tests.test_webhook tests.test_console_api -v`

Expected: PASS with ledger-backed events for webhook and manual flows.

- [ ] **Step 5: Commit**

```bash
git add src/agentflow/services/webhook.py src/agentflow/store.py src/agentflow/console.py tests/test_webhook.py tests/test_console_api.py
git commit -m "feat: record webhook and manual governance events"
```

### Task 5: Switch API, SSE, and Task Detail to Unified Event Objects

**Files:**
- Modify: `src/agentflow/console.py`
- Modify: `tests/test_console_api.py`
- Modify: `tests/test_console_flow.py`

- [ ] **Step 1: Write failing API/SSE tests for unified event payloads**

Add tests asserting:

```python
events = broker.since("demo", 0)
self.assertEqual("gate.failed", events[0]["event_type"])
self.assertIn("evidence", events[0])
self.assertIn("summary", events[0])
```

And for task detail:

```python
payload = self._get_json(f"/api/task/{task_id}")
self.assertIn("timeline", payload)
self.assertIn("derived_summary", payload)
```

- [ ] **Step 2: Run the console API/flow tests to verify failure**

Run:
`cd "$(git rev-parse --show-toplevel)" && PYTHONPATH=src python3 -m unittest tests.test_console_api tests.test_console_flow -v`

Expected: FAIL because `/api/events` still streams `event + payload` and `/api/task/<id>` does not return ledger timeline data.

- [ ] **Step 3: Update `EventBroker` and HTTP handlers**

Refactor `src/agentflow/console.py` so:

- `EventBroker.publish()` accepts a normalized ledger event object
- `EventBroker.since()` reads from `list_project_events(...)`
- `/api/events` streams a single standard event object
- `/api/audit` returns ledger audit events instead of `status_history`
- `/api/task/<id>` returns:

```json
{
  "task": {...},
  "timeline": [...],
  "recent_runs": [...],
  "derived_summary": {...}
}
```

- [ ] **Step 4: Run the console API/flow tests to verify pass**

Run:
`cd "$(git rev-parse --show-toplevel)" && PYTHONPATH=src python3 -m unittest tests.test_console_api tests.test_console_flow -v`

Expected: PASS with unified event payloads in both polling and SSE code paths.

- [ ] **Step 5: Commit**

```bash
git add src/agentflow/console.py tests/test_console_api.py tests/test_console_flow.py
git commit -m "feat: unify api and sse around ledger events"
```

### Task 6: Update CLI Inspection Commands to Use Ledger Events

**Files:**
- Modify: `src/agentflow/cli.py`
- Modify: `tests/test_cli_smoke.py`

- [ ] **Step 1: Write failing CLI smoke tests**

Update `tests/test_cli_smoke.py` so:

- `audit` asserts `event_type=` output instead of only `from=... to=...`
- `run-steps` is either replaced with or complemented by a ledger event inspection command
- `recent-runs` still works, but detail output references unified event evidence

Example:

```python
audit_out = self._run_cli("audit", "--project", "demo", "--limit", "5")
self.assertIn("event_type=task.status_changed", audit_out)
```

- [ ] **Step 2: Run the CLI smoke tests to verify failure**

Run:
`cd "$(git rev-parse --show-toplevel)" && PYTHONPATH=src python3 -m unittest tests.test_cli_smoke -v`

Expected: FAIL because CLI still reads old audit/run-step projections.

- [ ] **Step 3: Update CLI output and commands**

Refactor `src/agentflow/cli.py` so:

- `audit` reads `list_project_audit_events(...)`
- `task-detail` includes task timeline/derived summary
- keep `recent-runs` as snapshot output
- either deprecate `run-steps` in help text or back it with ledger timeline for the run

- [ ] **Step 4: Run the CLI smoke tests to verify pass**

Run:
`cd "$(git rev-parse --show-toplevel)" && PYTHONPATH=src python3 -m unittest tests.test_cli_smoke -v`

Expected: PASS with ledger-backed inspection output.

- [ ] **Step 5: Commit**

```bash
git add src/agentflow/cli.py tests/test_cli_smoke.py
git commit -m "feat: switch cli inspection commands to ledger events"
```

### Task 7: Convert the Console to Evidence-First Rendering

**Files:**
- Modify: `src/agentflow/web/static/console.js`
- Modify: `src/agentflow/console.py`
- Modify: `tests/test_console_api.py`

- [ ] **Step 1: Write failing UI-facing API assertions**

Add API tests that verify task detail returns:

```python
self.assertIn("latest_progress", payload["derived_summary"])
self.assertIn("latest_risk", payload["derived_summary"])
self.assertIn("recommended_actions", payload["derived_summary"])
```

This keeps the browser changes grounded in stable API outputs.

- [ ] **Step 2: Run the console API tests to verify failure**

Run:
`cd "$(git rev-parse --show-toplevel)" && PYTHONPATH=src python3 -m unittest tests.test_console_api -v`

Expected: FAIL because the derived summary contract is not implemented yet.

- [ ] **Step 3: Update browser rendering**

Modify `src/agentflow/web/static/console.js` to:

- render audit list from unified `event_type/summary/severity`
- render task detail timeline from `timeline`
- show derived panels for latest progress, latest handoff, latest risk, and recommended actions
- refresh from SSE without needing to understand legacy payload wrappers

- [ ] **Step 4: Run the console API tests to verify pass**

Run:
`cd "$(git rev-parse --show-toplevel)" && PYTHONPATH=src python3 -m unittest tests.test_console_api -v`

Expected: PASS with UI-facing API shape stable for the new evidence-first console.

- [ ] **Step 5: Commit**

```bash
git add src/agentflow/web/static/console.js src/agentflow/console.py tests/test_console_api.py
git commit -m "feat: render evidence-first console from ledger events"
```

### Task 8: Documentation Sync and Full Verification

**Files:**
- Modify: `README.md`
- Modify: `README.zh-CN.md`
- Modify: `docs/superpowers/specs/2026-04-02-event-model-v1-design.md`

- [ ] **Step 1: Update docs to describe the new event model**

Document:

- `ledger_events` as the event source of truth
- `tasks/runs` as snapshot tables
- updated `/api/events`, `/api/audit`, and task detail semantics
- any CLI command changes

- [ ] **Step 2: Run the full test suite**

Run:
`cd "$(git rev-parse --show-toplevel)" && PYTHONPATH=src python3 -m unittest discover -s tests -p 'test_*.py' -v`

Expected: PASS.

- [ ] **Step 3: Run a manual smoke flow**

Run:

```bash
cd "$(git rev-parse --show-toplevel)"
agentflow --db ./data/agentflow.db init
agentflow --db ./data/agentflow.db create-project demo --repo example/demo
agentflow --db ./data/agentflow.db add-task --project demo --title "event model smoke" --priority 4 --impact 4 --effort 2
agentflow --db ./data/agentflow.db run-once --project demo --adapter mock --agent codex-a
agentflow --db ./data/agentflow.db audit --project demo --limit 10
```

Expected:

- run completes
- `audit` shows unified ledger event types and summaries
- console task detail shows timeline and derived summary

- [ ] **Step 4: Commit**

```bash
git add README.md README.zh-CN.md docs/superpowers/specs/2026-04-02-event-model-v1-design.md
git commit -m "docs: sync event model design and user docs"
```

## Notes

- Keep `status_history`, `run_steps`, and legacy `events` only as temporary compatibility projections if needed during implementation. New behavior must be driven by `ledger_events`.
- Prefer small commits after each task; this plan assumes TDD throughout.
- A plan-review subagent was not used here because this session did not include explicit permission to delegate to subagents.
