from __future__ import annotations

import hashlib
import hmac
import json
from dataclasses import asdict
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import parse_qs, urlparse

from agentflow.adapters.registry import AdapterRegistry
from agentflow.services.discovery import IssueDiscoveryService
from agentflow.services.runner import Runner
from agentflow.services.webhook import GithubCommentWebhookService
from agentflow.store import Store

INDEX_HTML = """<!doctype html>
<html lang=\"en\">
<head>
  <meta charset=\"utf-8\" />
  <meta name=\"viewport\" content=\"width=device-width,initial-scale=1\" />
  <title>AgentFlow Console</title>
  <style>
    :root {
      --bg: #f3f7fb;
      --card: #ffffff;
      --ink: #132238;
      --muted: #5b6b7e;
      --line: #d8e2ef;
      --accent: #007a6e;
      --warn: #c04848;
      --ok: #2a7b3f;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      color: var(--ink);
      background: radial-gradient(circle at 10% 10%, #e7f2ff, #f4f8fb 40%, #f3f7fb 75%);
      font-family: "Space Grotesk", "IBM Plex Sans", "Segoe UI", sans-serif;
    }
    .topbar {
      display: flex;
      align-items: center;
      justify-content: space-between;
      padding: 14px 18px;
      border-bottom: 1px solid var(--line);
      background: rgba(255,255,255,0.9);
      backdrop-filter: blur(5px);
      position: sticky;
      top: 0;
      z-index: 10;
      gap: 10px;
    }
    .brand { font-size: 20px; font-weight: 700; letter-spacing: 0.3px; }
    .sub { color: var(--muted); font-size: 12px; }
    .toolbar { display:flex; gap:8px; align-items:center; flex-wrap:wrap; }
    .grid {
      display: grid;
      grid-template-columns: repeat(4, minmax(0, 1fr));
      gap: 10px;
      padding: 12px 14px 0;
    }
    .card {
      background: var(--card);
      border: 1px solid var(--line);
      border-radius: 12px;
      padding: 10px 12px;
      box-shadow: 0 4px 14px rgba(17, 42, 71, 0.06);
    }
    .card .k { font-size: 11px; color: var(--muted); }
    .card .v { font-size: 24px; font-weight: 700; margin-top: 2px; }
    .layout {
      display: grid;
      grid-template-columns: 33% 1fr;
      gap: 14px;
      padding: 14px;
      min-height: 460px;
    }
    .panel {
      background: var(--card);
      border: 1px solid var(--line);
      border-radius: 14px;
      overflow: hidden;
      box-shadow: 0 8px 24px rgba(17, 42, 71, 0.08);
    }
    .panel h3 { margin: 0; padding: 12px 14px; border-bottom: 1px solid var(--line); }
    .filters { padding: 10px 14px; border-bottom: 1px solid var(--line); display: flex; gap: 8px; }
    input, select {
      width: 100%; padding: 8px; border: 1px solid var(--line); border-radius: 8px; background: #fff;
      font-family: inherit;
    }
    .task-list { max-height: calc(100vh - 280px); overflow: auto; }
    .task { padding: 10px 14px; border-bottom: 1px solid #eef3f9; cursor: pointer; }
    .task:hover { background: #f7fbff; }
    .task.active { background: #e9f7f4; border-left: 4px solid var(--accent); padding-left: 10px; }
    .task-title { font-weight: 600; }
    .meta { font-size: 12px; color: var(--muted); margin-top: 4px; display: flex; gap: 10px; flex-wrap:wrap; }
    .detail { position: relative; }
    .detail-content { padding: 14px; }
    .badge { font-size: 11px; padding: 2px 8px; border-radius: 999px; border: 1px solid var(--line); color: var(--muted); }
    .detail-top { display: flex; align-items: center; justify-content: space-between; gap: 8px; }
    .detail-title { font-size: 20px; font-weight: 700; margin: 8px 0 4px; }
    .detail-grid { display: grid; grid-template-columns: repeat(3, minmax(0,1fr)); gap: 8px; margin-top: 10px; }
    .stat { border: 1px solid var(--line); border-radius: 10px; padding: 10px; }
    .stat .k { font-size: 11px; color: var(--muted); }
    .stat .v { font-weight: 700; margin-top: 3px; }
    .detail-actions { display: flex; gap: 8px; margin-top: 12px; }
    button {
      border: none;
      border-radius: 10px;
      padding: 8px 12px;
      cursor: pointer;
      color: #fff;
      background: var(--accent);
      font-weight: 600;
      font-family: inherit;
    }
    button.secondary { background: #4b6686; }
    .history { margin-top: 14px; border-top: 1px solid var(--line); padding-top: 10px; }
    .timeline-item { font-size: 13px; padding: 7px 0; border-bottom: 1px dashed #edf2f7; }
    .err { color: var(--warn); font-weight: 600; }
    .ok { color: var(--ok); font-weight: 600; }
    .board-wrap {
      display: grid;
      grid-template-columns: repeat(4, minmax(0, 1fr));
      gap: 10px;
      padding: 0 14px 14px;
    }
    .col {
      background: #f9fbff;
      border: 1px solid var(--line);
      border-radius: 12px;
      min-height: 120px;
    }
    .col h4 {
      margin: 0;
      padding: 10px;
      border-bottom: 1px solid var(--line);
      font-size: 13px;
    }
    .chip {
      margin: 8px;
      border: 1px solid var(--line);
      border-radius: 10px;
      background: #fff;
      padding: 8px;
      font-size: 12px;
      cursor: pointer;
    }
    .split {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 14px;
      padding: 0 14px 14px;
    }
    .list {
      max-height: 240px;
      overflow: auto;
      padding: 10px;
    }
    .run-item {
      padding: 8px 0;
      border-bottom: 1px solid #ecf2f9;
      font-size: 13px;
    }
    @media (max-width: 1200px) {
      .grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
      .layout { grid-template-columns: 1fr; }
      .board-wrap { grid-template-columns: repeat(2, minmax(0, 1fr)); }
      .split { grid-template-columns: 1fr; }
      .detail-grid { grid-template-columns: repeat(2, minmax(0,1fr)); }
    }
    @media (max-width: 700px) {
      .grid { grid-template-columns: 1fr; }
      .board-wrap { grid-template-columns: 1fr; }
      .detail-grid { grid-template-columns: 1fr; }
    }
  </style>
</head>
<body>
  <div class=\"topbar\">
    <div>
      <div class=\"brand\">AgentFlow Console</div>
      <div class=\"sub\">Task center + visual board + recent run stream</div>
    </div>
    <div class=\"toolbar\">
      <label class=\"sub\">Project</label>
      <select id=\"projectSelect\"></select>
      <button class=\"secondary\" onclick=\"refreshAll()\">Refresh</button>
      <button class=\"secondary\" id=\"autoBtn\" onclick=\"toggleAuto()\">Auto: OFF</button>
    </div>
  </div>

  <section class=\"grid\" id=\"cards\"></section>

  <div class=\"layout\">
    <section class=\"panel\">
      <h3>Task Queue</h3>
      <div class=\"filters\">
        <input id=\"q\" placeholder=\"search title...\" oninput=\"renderTaskList()\" />
        <select id=\"statusFilter\" onchange=\"renderTaskList()\">
          <option value=\"\">all status</option>
        </select>
      </div>
      <div id=\"taskList\" class=\"task-list\"></div>
    </section>

    <section class=\"panel detail\">
      <h3>Task Detail</h3>
      <div id=\"detail\" class=\"detail-content\"><div class=\"sub\">Select a task to inspect execution details.</div></div>
    </section>
  </div>

  <section class=\"panel\" style=\"margin: 0 14px 14px\">
    <h3>Status Board</h3>
    <div id=\"board\" class=\"board-wrap\"></div>
  </section>

  <section class=\"split\">
    <section class=\"panel\">
      <h3>Recent Runs</h3>
      <div id=\"recentRuns\" class=\"list\"></div>
    </section>
    <section class=\"panel\">
      <h3>Webhook Guide</h3>
      <div class=\"list\">
        <div class=\"timeline-item\"><span class=\"sub\">Comment trigger:</span><br/>POST <code>/webhook/github/comment?project=&lt;name&gt;&adapter=mock&agent=bot</code></div>
        <div class=\"timeline-item\"><span class=\"sub\">Discovery trigger:</span><br/>POST <code>/webhook/github/issues?project=&lt;name&gt;</code></div>
        <div class=\"timeline-item\"><span class=\"sub\">Auto event endpoint:</span><br/>POST <code>/webhook/github?project=&lt;name&gt;&adapter=mock&agent=bot</code> with <code>X-GitHub-Event</code></div>
      </div>
    </section>
  </section>

  <script>
    const state = {
      projects: [],
      tasks: [],
      filtered: [],
      selectedTask: null,
      autoTimer: null,
      recentRuns: [],
      stats: {},
    };

    async function api(url, opts) {
      const res = await fetch(url, opts);
      if (!res.ok) throw new Error(await res.text());
      return await res.json();
    }

    function statusClass(status) { return status === 'blocked' ? 'err' : ''; }

    async function loadProjects() {
      const data = await api('/api/projects');
      state.projects = data.projects || [];
      const sel = document.getElementById('projectSelect');
      const current = sel.value;
      sel.innerHTML = state.projects.map(p => `<option value=\"${p}\">${p}</option>`).join('');
      if (current && state.projects.includes(current)) sel.value = current;
      sel.onchange = refreshAll;
    }

    function currentProject() {
      return document.getElementById('projectSelect').value;
    }

    async function loadTasks() {
      const data = await api(`/api/tasks?project=${encodeURIComponent(currentProject())}`);
      state.tasks = data.tasks || [];
      const statuses = [...new Set(state.tasks.map(t => t.status))].sort();
      const statusSel = document.getElementById('statusFilter');
      const old = statusSel.value;
      statusSel.innerHTML = '<option value="">all status</option>' + statuses.map(s => `<option value=\"${s}\">${s}</option>`).join('');
      if (statuses.includes(old)) statusSel.value = old;
      renderTaskList();
      renderBoard();
    }

    async function loadStatsAndRuns() {
      const project = currentProject();
      const statsData = await api(`/api/stats?project=${encodeURIComponent(project)}`);
      const runsData = await api(`/api/runs/recent?project=${encodeURIComponent(project)}&limit=20`);
      state.stats = statsData;
      state.recentRuns = runsData.runs || [];
      renderCards();
      renderRecentRuns();
    }

    function renderCards() {
      const counts = state.stats.status_counts || {};
      const cards = [
        { k: 'Pending', v: counts.pending || 0 },
        { k: 'In Progress', v: counts.in_progress || 0 },
        { k: 'Blocked', v: counts.blocked || 0 },
        { k: 'Recent Runs (24h)', v: state.stats.recent_run_count || 0 },
      ];
      const root = document.getElementById('cards');
      root.innerHTML = cards.map(c => `<div class=\"card\"><div class=\"k\">${c.k}</div><div class=\"v\">${c.v}</div></div>`).join('');
    }

    function renderTaskList() {
      const q = document.getElementById('q').value.trim().toLowerCase();
      const st = document.getElementById('statusFilter').value;
      state.filtered = state.tasks.filter(t => {
        if (st && t.status !== st) return false;
        if (q && !t.title.toLowerCase().includes(q)) return false;
        return true;
      });
      const root = document.getElementById('taskList');
      if (!state.filtered.length) {
        root.innerHTML = '<div class=\"task\"><span class=\"sub\">No tasks</span></div>';
        return;
      }
      root.innerHTML = state.filtered.map(t => `
        <div class=\"task ${state.selectedTask && state.selectedTask.id === t.id ? 'active' : ''}\" onclick=\"openTask(${t.id})\">
          <div class=\"task-title\">#${t.id} ${t.title}</div>
          <div class=\"meta\">
            <span class=\"${statusClass(t.status)}\">${t.status}</span>
            <span>p${t.priority}/i${t.impact}/e${t.effort}</span>
            <span>${t.assigned_agent || '-'}</span>
          </div>
        </div>`).join('');
    }

    function renderBoard() {
      const statuses = ['pending', 'approved', 'in_progress', 'blocked'];
      const root = document.getElementById('board');
      root.innerHTML = statuses.map(st => {
        const tasks = state.tasks.filter(t => t.status === st).slice(0, 8);
        const items = tasks.map(t => `<div class=\"chip\" onclick=\"openTask(${t.id})\">#${t.id} ${t.title}</div>`).join('') || '<div class=\"sub\" style=\"padding:10px\">(empty)</div>';
        return `<section class=\"col\"><h4>${st} (${tasks.length})</h4>${items}</section>`;
      }).join('');
    }

    function renderRecentRuns() {
      const root = document.getElementById('recentRuns');
      if (!state.recentRuns.length) {
        root.innerHTML = '<div class=\"sub\">No runs yet</div>';
        return;
      }
      root.innerHTML = state.recentRuns.map(r => `
        <div class=\"run-item\">
          <div><strong>#${r.id}</strong> task #${r.task_id} ${r.task_title || ''}</div>
          <div class=\"meta\"><span>${r.status}</span><span>${r.adapter}</span><span>${r.agent_name}</span><span>${r.started_at}</span></div>
        </div>
      `).join('');
    }

    async function openTask(taskId) {
      const data = await api(`/api/task/${taskId}`);
      state.selectedTask = data.task;
      renderTaskList();
      renderDetail(data);
    }

    function renderDetail(data) {
      const t = data.task;
      const detail = document.getElementById('detail');
      detail.innerHTML = `
        <div class=\"detail-top\">
          <span class=\"badge\">task #${t.id}</span>
          <span class=\"badge ${statusClass(t.status)}\">${t.status}</span>
        </div>
        <div class=\"detail-title\">${t.title}</div>
        <div class=\"sub\">source: ${t.source || '-'} ${t.external_id || ''}</div>
        ${t.pr_url ? `<div class=\"sub\">PR: <a href=\"${t.pr_url}\" target=\"_blank\">${t.pr_url}</a></div>` : ''}
        <div class=\"detail-grid\">
          <div class=\"stat\"><div class=\"k\">Priority</div><div class=\"v\">${t.priority}</div></div>
          <div class=\"stat\"><div class=\"k\">Impact</div><div class=\"v\">${t.impact}</div></div>
          <div class=\"stat\"><div class=\"k\">Effort</div><div class=\"v\">${t.effort}</div></div>
          <div class=\"stat\"><div class=\"k\">Agent</div><div class=\"v\">${t.assigned_agent || '-'}</div></div>
          <div class=\"stat\"><div class=\"k\">Lease</div><div class=\"v\">${t.lease_until || '-'}</div></div>
          <div class=\"stat\"><div class=\"k\">Runs</div><div class=\"v\">${data.runs.length}</div></div>
        </div>
        <div class=\"detail-actions\">
          <select id=\"adapterSel\"><option value=\"mock\">mock</option></select>
          <input id=\"agentInput\" placeholder=\"agent name\" value=\"web-console-agent\" />
          <button onclick=\"runTask(${t.id})\">Run Task</button>
        </div>
        <div class=\"history\">
          <h4 style=\"margin:0 0 8px\">Status History</h4>
          ${(data.history || []).map(h => `<div class=\"timeline-item\">${h.changed_at}: ${h.from_status || '-'} -> ${h.to_status} ${h.note ? `| ${h.note}` : ''}</div>`).join('') || '<div class=\"sub\">No history</div>'}
        </div>
        <div class=\"history\">
          <h4 style=\"margin:0 0 8px\">Run Timeline</h4>
          ${(data.runs || []).map(r => `
            <div class=\"timeline-item\">
              <span class=\"${r.status === 'failed' ? 'err' : 'ok'}\">run #${r.id} ${r.status}</span>
              <div class=\"sub\">${r.trigger_type} | ${r.adapter} | ${r.agent_name} | gate=${r.gate_passed ? 'pass' : 'fail'}</div>
              <div class=\"sub\">${(r.steps || []).map(s => `${s.step_name}:${s.status}`).join(' | ') || 'no steps'}</div>
            </div>
          `).join('') || '<div class=\"sub\">No runs yet</div>'}
        </div>
      `;
    }

    async function runTask(taskId) {
      const project = currentProject();
      const adapter = document.getElementById('adapterSel').value;
      const agent = document.getElementById('agentInput').value || 'web-console-agent';
      try {
        const res = await api(`/api/task/${taskId}/run`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ project, adapter, agent })
        });
        await refreshAll();
        await openTask(taskId);
        alert(res.message || 'run completed');
      } catch (err) {
        alert(`run failed: ${err}`);
      }
    }

    async function refreshAll() {
      await loadTasks();
      await loadStatsAndRuns();
      if (state.selectedTask) {
        const exists = state.tasks.find(t => t.id === state.selectedTask.id);
        if (exists) await openTask(state.selectedTask.id);
      }
    }

    function toggleAuto() {
      const btn = document.getElementById('autoBtn');
      if (state.autoTimer) {
        clearInterval(state.autoTimer);
        state.autoTimer = null;
        btn.textContent = 'Auto: OFF';
        return;
      }
      state.autoTimer = setInterval(() => {
        refreshAll().catch(err => console.error(err));
      }, 15000);
      btn.textContent = 'Auto: ON';
    }

    async function boot() {
      await loadProjects();
      await refreshAll();
    }

    boot().catch(err => {
      document.body.innerHTML = `<pre class=\"err\">Failed to load console: ${err}</pre>`;
    });
  </script>
</body>
</html>
"""


def _task_to_dict(task: Any) -> dict[str, Any]:
    if hasattr(task, "__dataclass_fields__"):
        return asdict(task)
    return dict(task)


def _row_to_dict(row: Any) -> dict[str, Any]:
    return dict(row)


def _verify_signature(secret: str | None, body: bytes, signature_header: str | None) -> bool:
    if not secret:
        return True
    if not signature_header or not signature_header.startswith("sha256="):
        return False
    expected = "sha256=" + hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature_header)


def _build_handler(
    store: Store,
    runner: Runner,
    discovery: IssueDiscoveryService,
    webhook: GithubCommentWebhookService,
    github_webhook_secret: str | None,
):
    class ConsoleHandler(BaseHTTPRequestHandler):
        server_version = "AgentFlowConsole/0.2"

        def _send_json(self, payload: dict[str, Any], status: int = HTTPStatus.OK) -> None:
            data = json.dumps(payload).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def _send_html(self, html: str) -> None:
            data = html.encode("utf-8")
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def _read_body(self) -> bytes:
            length = int(self.headers.get("Content-Length", "0"))
            return self.rfile.read(length) if length > 0 else b""

        def _parse_json(self, body: bytes) -> dict[str, Any]:
            if not body:
                return {}
            loaded = json.loads(body.decode("utf-8"))
            return loaded if isinstance(loaded, dict) else {"payload": loaded}

        def do_GET(self) -> None:  # noqa: N802
            parsed = urlparse(self.path)
            path = parsed.path
            query = parse_qs(parsed.query)

            if path == "/":
                self._send_html(INDEX_HTML)
                return

            if path == "/api/projects":
                self._send_json({"projects": list(store.projects())})
                return

            if path == "/api/tasks":
                project = query.get("project", [None])[0]
                tasks = [_task_to_dict(t) for t in store.list_tasks(project)]
                self._send_json({"tasks": tasks})
                return

            if path == "/api/stats":
                project = query.get("project", [None])[0]
                if not project:
                    self._send_json({"error": "project is required"}, status=HTTPStatus.BAD_REQUEST)
                    return
                counts = store.status_counts(project)
                recent_runs = store.list_recent_runs(project, limit=50)
                payload = {
                    "project": project,
                    "status_counts": counts,
                    "recent_run_count": len(recent_runs),
                    "workers": [_task_to_dict(t) for t in store.list_in_progress(project)],
                }
                self._send_json(payload)
                return

            if path == "/api/runs/recent":
                project = query.get("project", [None])[0]
                if not project:
                    self._send_json({"error": "project is required"}, status=HTTPStatus.BAD_REQUEST)
                    return
                raw_limit = query.get("limit", ["20"])[0]
                try:
                    limit = max(1, min(200, int(raw_limit)))
                except ValueError:
                    limit = 20
                rows = [_row_to_dict(r) for r in store.list_recent_runs(project, limit=limit)]
                self._send_json({"runs": rows})
                return

            if path.startswith("/api/task/"):
                parts = path.strip("/").split("/")
                if len(parts) == 3:
                    try:
                        task_id = int(parts[2])
                    except ValueError:
                        self._send_json({"error": "invalid task id"}, status=HTTPStatus.BAD_REQUEST)
                        return
                    task = store.get_task(task_id)
                    if task is None:
                        self._send_json({"error": "task not found"}, status=HTTPStatus.NOT_FOUND)
                        return
                    runs = [_row_to_dict(r) for r in store.list_runs(task_id)]
                    for run in runs:
                        run["steps"] = [_row_to_dict(s) for s in store.list_run_steps(int(run["id"]))]
                    history = [_row_to_dict(h) for h in store.list_status_history(task_id)]
                    self._send_json({"task": _task_to_dict(task), "runs": runs, "history": history})
                    return

            self._send_json({"error": "not found"}, status=HTTPStatus.NOT_FOUND)

        def do_POST(self) -> None:  # noqa: N802
            parsed = urlparse(self.path)
            path = parsed.path
            query = parse_qs(parsed.query)
            body = self._read_body()

            if path.startswith("/api/task/") and path.endswith("/run"):
                parts = path.strip("/").split("/")
                if len(parts) != 4:
                    self._send_json({"error": "invalid path"}, status=HTTPStatus.BAD_REQUEST)
                    return
                try:
                    task_id = int(parts[2])
                except ValueError:
                    self._send_json({"error": "invalid task id"}, status=HTTPStatus.BAD_REQUEST)
                    return
                payload = self._parse_json(body)
                task = store.get_task(task_id)
                if task is None:
                    self._send_json({"error": "task not found"}, status=HTTPStatus.NOT_FOUND)
                    return
                project = str(payload.get("project") or task.project)
                adapter = str(payload.get("adapter") or "mock")
                agent = str(payload.get("agent") or "web-console-agent")
                run = runner.run_task(project, task_id, adapter, agent)
                self._send_json(
                    {
                        "ok": run.task is not None,
                        "message": run.message,
                        "success": run.success,
                        "task": _task_to_dict(run.task) if run.task is not None else None,
                    }
                )
                return

            if path in {"/webhook/github", "/webhook/github/comment", "/webhook/github/issues"}:
                if not _verify_signature(
                    github_webhook_secret,
                    body,
                    self.headers.get("X-Hub-Signature-256"),
                ):
                    self._send_json({"ok": False, "error": "invalid signature"}, status=HTTPStatus.UNAUTHORIZED)
                    return

                payload = self._parse_json(body)
                project = query.get("project", [None])[0]
                if not project:
                    self._send_json({"ok": False, "error": "project query parameter is required"}, status=HTTPStatus.BAD_REQUEST)
                    return

                adapter = query.get("adapter", ["mock"])[0]
                agent = query.get("agent", ["webhook-agent"])[0]

                if path == "/webhook/github/issues":
                    issues_obj = payload.get("issues")
                    if isinstance(issues_obj, list):
                        issues = [i for i in issues_obj if isinstance(i, dict)]
                    elif isinstance(payload, dict) and all(k in payload for k in ("number", "title")):
                        issues = [payload]
                    else:
                        issues = []
                    result = discovery.ingest_issues(project, issues)
                    self._send_json({"ok": True, "created": result.created, "skipped": result.skipped})
                    return

                if path == "/webhook/github/comment":
                    result = webhook.handle_pr_comment(project=project, payload=payload, adapter=adapter, agent_name=agent)
                    self._send_json(
                        {
                            "ok": True,
                            "accepted": result.accepted,
                            "duplicate": result.duplicate,
                            "run_success": result.run_success,
                            "message": result.message,
                        }
                    )
                    return

                event = self.headers.get("X-GitHub-Event", "")
                if event in {"issue_comment", "pull_request_review_comment"}:
                    result = webhook.handle_pr_comment(project=project, payload=payload, adapter=adapter, agent_name=agent)
                    self._send_json(
                        {
                            "ok": True,
                            "event": event,
                            "accepted": result.accepted,
                            "duplicate": result.duplicate,
                            "run_success": result.run_success,
                            "message": result.message,
                        }
                    )
                    return

                if event == "issues":
                    action = str(payload.get("action", ""))
                    issue = payload.get("issue")
                    if action in {"opened", "reopened"} and isinstance(issue, dict):
                        result = discovery.ingest_issues(project, [issue])
                        self._send_json({"ok": True, "event": event, "created": result.created, "skipped": result.skipped})
                        return
                    self._send_json({"ok": True, "event": event, "message": "ignored issues action"})
                    return

                if event == "ping":
                    self._send_json({"ok": True, "event": "ping"})
                    return

                self._send_json({"ok": True, "event": event or "unknown", "message": "ignored event"})
                return

            self._send_json({"error": "not found"}, status=HTTPStatus.NOT_FOUND)

        def log_message(self, _format: str, *_args: Any) -> None:
            # Keep CLI output clean for interactive use.
            return

    return ConsoleHandler


def serve_console(
    host: str,
    port: int,
    db_path: str,
    github_webhook_secret: str | None = None,
) -> None:
    store = Store(db_path)
    registry = AdapterRegistry()
    runner = Runner(store, registry)
    discovery = IssueDiscoveryService(store)
    webhook = GithubCommentWebhookService(store, runner)
    handler = _build_handler(store, runner, discovery, webhook, github_webhook_secret)
    server = ThreadingHTTPServer((host, port), handler)
    print(f"AgentFlow console running on http://{host}:{port}")
    print(f"Using db: {db_path}")
    print(f"GitHub webhook secret: {'enabled' if github_webhook_secret else 'disabled'}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
