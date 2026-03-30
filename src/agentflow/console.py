from __future__ import annotations

import json
from dataclasses import asdict
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import parse_qs, urlparse

from agentflow.adapters.registry import AdapterRegistry
from agentflow.services.runner import Runner
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
    }
    .brand { font-size: 20px; font-weight: 700; letter-spacing: 0.3px; }
    .sub { color: var(--muted); font-size: 12px; }
    .layout {
      display: grid;
      grid-template-columns: 34% 1fr;
      gap: 14px;
      padding: 14px;
      min-height: calc(100vh - 62px);
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
    .filters input, .filters select, .detail-actions select {
      width: 100%; padding: 8px; border: 1px solid var(--line); border-radius: 8px; background: #fff;
    }
    .task-list { max-height: calc(100vh - 220px); overflow: auto; }
    .task { padding: 10px 14px; border-bottom: 1px solid #eef3f9; cursor: pointer; }
    .task:hover { background: #f7fbff; }
    .task.active { background: #e9f7f4; border-left: 4px solid var(--accent); padding-left: 10px; }
    .task-title { font-weight: 600; }
    .meta { font-size: 12px; color: var(--muted); margin-top: 4px; display: flex; gap: 10px; }
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
      border: none; border-radius: 10px; padding: 8px 12px; cursor: pointer; color: #fff; background: var(--accent);
      font-weight: 600;
    }
    button.secondary { background: #4b6686; }
    .history { margin-top: 14px; border-top: 1px solid var(--line); padding-top: 10px; }
    .timeline-item { font-size: 13px; padding: 7px 0; border-bottom: 1px dashed #edf2f7; }
    .drawer {
      position: absolute;
      top: 0;
      right: 0;
      width: 42%;
      height: 100%;
      border-left: 1px solid var(--line);
      background: #fbfdff;
      transform: translateX(100%);
      transition: transform 0.22s ease;
      display: flex;
      flex-direction: column;
    }
    .drawer.open { transform: translateX(0); }
    .drawer-head { padding: 12px 14px; border-bottom: 1px solid var(--line); font-weight: 700; }
    .drawer-body { overflow: auto; padding: 10px 14px; }
    .run-item { padding: 8px 0; border-bottom: 1px solid #ecf2f9; }
    .run-item .run-head { display:flex; justify-content: space-between; font-size: 12px; color: var(--muted); }
    .run-item .run-main { margin-top: 4px; font-weight: 600; }
    .step-list { margin-top: 6px; padding-left: 14px; color: var(--muted); font-size: 12px; }
    .err { color: var(--warn); font-weight: 600; }
    @media (max-width: 1100px) {
      .layout { grid-template-columns: 1fr; }
      .drawer { width: 100%; }
    }
  </style>
</head>
<body>
  <div class=\"topbar\">
    <div>
      <div class=\"brand\">AgentFlow Console</div>
      <div class=\"sub\">Task-first execution view with run timeline</div>
    </div>
    <div style=\"display:flex; gap:8px; align-items:center\">
      <label class=\"sub\">Project</label>
      <select id=\"projectSelect\"></select>
      <button class=\"secondary\" onclick=\"refreshAll()\">Refresh</button>
    </div>
  </div>

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
      <aside id=\"drawer\" class=\"drawer\">
        <div class=\"drawer-head\">Run Timeline</div>
        <div id=\"runList\" class=\"drawer-body\"></div>
      </aside>
    </section>
  </div>

  <script>
    const state = { projects: [], tasks: [], filtered: [], selectedTask: null };

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
      sel.innerHTML = state.projects.map(p => `<option value="${p}">${p}</option>`).join('');
      sel.onchange = refreshAll;
    }

    async function loadTasks() {
      const project = document.getElementById('projectSelect').value;
      const data = await api(`/api/tasks?project=${encodeURIComponent(project)}`);
      state.tasks = data.tasks || [];
      const statuses = [...new Set(state.tasks.map(t => t.status))].sort();
      const statusSel = document.getElementById('statusFilter');
      const old = statusSel.value;
      statusSel.innerHTML = '<option value="">all status</option>' + statuses.map(s => `<option value="${s}">${s}</option>`).join('');
      if (statuses.includes(old)) statusSel.value = old;
      renderTaskList();
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
        root.innerHTML = '<div class="task"><span class="sub">No tasks</span></div>';
        return;
      }
      root.innerHTML = state.filtered.map(t => `
        <div class="task ${state.selectedTask && state.selectedTask.id === t.id ? 'active' : ''}" onclick="openTask(${t.id})">
          <div class="task-title">#${t.id} ${t.title}</div>
          <div class="meta">
            <span class="${statusClass(t.status)}">${t.status}</span>
            <span>p${t.priority}/i${t.impact}/e${t.effort}</span>
            <span>${t.assigned_agent || '-'}</span>
          </div>
        </div>`).join('');
    }

    async function openTask(taskId) {
      const data = await api(`/api/task/${taskId}`);
      state.selectedTask = data.task;
      renderTaskList();
      renderDetail(data);
      document.getElementById('drawer').classList.add('open');
    }

    function renderDetail(data) {
      const t = data.task;
      const detail = document.getElementById('detail');
      detail.innerHTML = `
        <div class="detail-top">
          <span class="badge">task #${t.id}</span>
          <span class="badge ${statusClass(t.status)}">${t.status}</span>
        </div>
        <div class="detail-title">${t.title}</div>
        <div class="sub">source: ${t.source || '-'} ${t.external_id || ''}</div>
        <div class="detail-grid">
          <div class="stat"><div class="k">Priority</div><div class="v">${t.priority}</div></div>
          <div class="stat"><div class="k">Impact</div><div class="v">${t.impact}</div></div>
          <div class="stat"><div class="k">Effort</div><div class="v">${t.effort}</div></div>
          <div class="stat"><div class="k">Agent</div><div class="v">${t.assigned_agent || '-'}</div></div>
          <div class="stat"><div class="k">Lease</div><div class="v">${t.lease_until || '-'}</div></div>
          <div class="stat"><div class="k">Runs</div><div class="v">${data.runs.length}</div></div>
        </div>
        <div class="detail-actions">
          <select id="adapterSel"><option value="mock">mock</option></select>
          <input id="agentInput" placeholder="agent name" value="web-console-agent" style="padding:8px;border:1px solid var(--line);border-radius:8px;"/>
          <button onclick="runTask(${t.id})">Run Task</button>
        </div>
        <div class="history">
          <h4 style="margin:0 0 8px">Status History</h4>
          ${(data.history || []).map(h => `<div class="timeline-item">${h.changed_at}: ${h.from_status || '-'} → ${h.to_status} ${h.note ? `| ${h.note}` : ''}</div>`).join('') || '<div class="sub">No history</div>'}
        </div>
      `;

      const runRoot = document.getElementById('runList');
      runRoot.innerHTML = (data.runs || []).map(r => `
        <div class="run-item">
          <div class="run-head"><span>run #${r.id}</span><span>${r.status}</span></div>
          <div class="run-main">${r.trigger_type} | ${r.adapter} | gate=${r.gate_passed ? 'pass' : 'fail'}</div>
          <div class="step-list">
            ${(r.steps || []).map(s => `<div>${s.step_name} · ${s.status}${s.log_excerpt ? ` · ${s.log_excerpt}` : ''}</div>`).join('') || '<div>no steps</div>'}
          </div>
        </div>
      `).join('') || '<div class="sub">No runs yet</div>';
    }

    async function runTask(taskId) {
      const project = document.getElementById('projectSelect').value;
      const adapter = document.getElementById('adapterSel').value;
      const agent = document.getElementById('agentInput').value || 'web-console-agent';
      try {
        const res = await api(`/api/task/${taskId}/run`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ project, adapter, agent })
        });
        await openTask(taskId);
        alert(res.message || 'run completed');
      } catch (err) {
        alert(`run failed: ${err}`);
      }
    }

    async function refreshAll() {
      await loadTasks();
      if (state.selectedTask) {
        const exists = state.tasks.find(t => t.id === state.selectedTask.id);
        if (exists) await openTask(state.selectedTask.id);
      }
    }

    async function boot() {
      await loadProjects();
      await loadTasks();
    }

    boot().catch(err => {
      document.body.innerHTML = `<pre class="err">Failed to load console: ${err}</pre>`;
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


def _build_handler(store: Store, runner: Runner):
    class ConsoleHandler(BaseHTTPRequestHandler):
        server_version = "AgentFlowConsole/0.1"

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

        def _parse_json_body(self) -> dict[str, Any]:
            length = int(self.headers.get("Content-Length", "0"))
            if length <= 0:
                return {}
            raw = self.rfile.read(length)
            return json.loads(raw.decode("utf-8")) if raw else {}

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
                body = self._parse_json_body()
                task = store.get_task(task_id)
                if task is None:
                    self._send_json({"error": "task not found"}, status=HTTPStatus.NOT_FOUND)
                    return
                project = str(body.get("project") or task.project)
                adapter = str(body.get("adapter") or "mock")
                agent = str(body.get("agent") or "web-console-agent")
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

            self._send_json({"error": "not found"}, status=HTTPStatus.NOT_FOUND)

        def log_message(self, _format: str, *_args: Any) -> None:
            # Keep CLI output clean for interactive use.
            return

    return ConsoleHandler


def serve_console(host: str, port: int, db_path: str) -> None:
    store = Store(db_path)
    registry = AdapterRegistry()
    runner = Runner(store, registry)
    handler = _build_handler(store, runner)
    server = ThreadingHTTPServer((host, port), handler)
    print(f"AgentFlow console running on http://{host}:{port}")
    print(f"Using db: {db_path}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
