from __future__ import annotations

import hashlib
import hmac
import json
import re
import sqlite3
import threading
import time
from dataclasses import asdict
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from agentflow.adapters.registry import AdapterRegistry
from agentflow.services.discovery import IssueDiscoveryService
from agentflow.services.ledger import derive_task_summary
from agentflow.services.runner import Runner
from agentflow.services.webhook import GithubCommentWebhookService
from agentflow.store import Store

INDEX_HTML = """<!doctype html>
<html lang=\"en\">
<head>
  <meta charset=\"utf-8\" />
  <meta name=\"viewport\" content=\"width=device-width,initial-scale=1\" />
  <title>🦊 AgentFlow Console</title>
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
      --c-todo: #2563eb;
      --c-ready: #7c3aed;
      --c-executing: #0f766e;
      --c-review: #b45309;
      --c-done: #15803d;
      --c-blocked: #b91c1c;
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
    .status-accordion { padding: 8px 10px 12px; }
    .status-group {
      border: 1px solid var(--line);
      border-radius: 12px;
      margin-bottom: 10px;
      background: #fbfdff;
      overflow: hidden;
    }
    .status-group[open] {
      box-shadow: 0 8px 20px rgba(17, 42, 71, 0.06);
    }
    .status-summary {
      list-style: none;
      cursor: pointer;
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 10px;
      padding: 10px 12px;
      border-bottom: 1px solid transparent;
      background: #f4f8ff;
    }
    .status-summary::-webkit-details-marker { display: none; }
    .status-group[open] .status-summary { border-bottom-color: var(--line); }
    .status-heading {
      display: flex;
      align-items: center;
      gap: 8px;
      font-weight: 700;
      text-transform: capitalize;
    }
    .status-count {
      font-size: 11px;
      color: var(--muted);
      border: 1px solid var(--line);
      border-radius: 999px;
      padding: 1px 7px;
      background: #fff;
    }
    .group-body { padding: 2px 0 4px; }
    .task { padding: 10px 14px; border-bottom: 1px solid #eef3f9; cursor: pointer; }
    .task:hover { background: #f7fbff; }
    .task.active { background: #e9f7f4; border-left: 4px solid var(--accent); padding-left: 10px; }
    .task-title { font-weight: 600; }
    .meta { font-size: 12px; color: var(--muted); margin-top: 4px; display: flex; gap: 10px; flex-wrap:wrap; }
    .detail { position: relative; }
    .detail-content { padding: 14px; }
    .badge { font-size: 11px; padding: 2px 8px; border-radius: 999px; border: 1px solid var(--line); color: var(--muted); }
    .badge-chip {
      font-size: 11px;
      padding: 2px 8px;
      border-radius: 999px;
      border: 1px solid transparent;
      font-weight: 600;
    }
    .stage-todo { background: #e8f0ff; color: var(--c-todo); border-color: #bfd4ff; }
    .stage-ready { background: #efe9ff; color: var(--c-ready); border-color: #d8c8ff; }
    .stage-executing, .stage-in_progress { background: #e4f7f4; color: var(--c-executing); border-color: #b5ece4; }
    .stage-review { background: #fff4e6; color: var(--c-review); border-color: #ffdcb1; }
    .stage-done { background: #e7f8ea; color: var(--c-done); border-color: #bdeec7; }
    .stage-blocked { background: #ffe8e8; color: var(--c-blocked); border-color: #ffc2c2; }
    .status-todo, .status-ready, .status-in-progress, .status-review, .status-done, .status-dropped, .status-blocked {
      font-weight: 600;
    }
    .status-todo { color: var(--c-todo); }
    .status-ready { color: var(--c-ready); }
    .status-in-progress { color: var(--c-executing); }
    .status-review { color: var(--c-review); }
    .status-done { color: var(--c-done); }
    .status-dropped { color: #64748b; }
    .status-blocked { color: var(--c-blocked); }
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
    a { color: #0b63c7; text-decoration: none; }
    a:hover { text-decoration: underline; }
    .err { color: var(--warn); font-weight: 600; }
    .ok { color: var(--ok); font-weight: 600; }
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
      .layout { grid-template-columns: 1fr; }
      .split { grid-template-columns: 1fr; }
      .detail-grid { grid-template-columns: repeat(2, minmax(0,1fr)); }
    }
    @media (max-width: 700px) {
      .detail-grid { grid-template-columns: 1fr; }
    }
  </style>
</head>
<body>
  <div class=\"topbar\">
    <div>
      <div class=\"brand\">🦊 AgentFlow Console</div>
      <div class=\"sub\">Task list + recent run stream</div>
    </div>
    <div class=\"toolbar\">
      <label class=\"sub\">Project</label>
      <select id=\"projectSelect\"></select>
      <span class=\"badge\" id=\"connState\">Stream: OFF</span>
      <button class=\"secondary\" onclick=\"refreshAll()\">Refresh</button>
      <button class=\"secondary\" id=\"autoBtn\" onclick=\"toggleAuto()\">Auto: OFF</button>
    </div>
  </div>

  <div class=\"layout\">
    <section class=\"panel\">
      <h3>Task List</h3>
      <div class=\"filters\">
        <input id=\"q\" placeholder=\"search title...\" oninput=\"renderTaskList()\" />
        <select id=\"sourceFilter\" onchange=\"renderTaskList()\">
          <option value=\"\">all sources</option>
        </select>
      </div>
      <div id=\"taskList\" class=\"task-list\"></div>
    </section>

    <section class=\"panel detail\">
      <h3>Task Detail</h3>
      <div id=\"detail\" class=\"detail-content\"><div class=\"sub\">Select a task to inspect execution details.</div></div>
    </section>
  </div>

  <section class=\"split\">
    <section class=\"panel\">
      <h3>Recent Runs</h3>
      <div id=\"recentRuns\" class=\"list\"></div>
    </section>
    <section class=\"panel\">
      <h3>Audit Trail</h3>
      <div id=\"auditList\" class=\"list\"></div>
    </section>
  </section>

  <script>
    const state = {
      projects: [],
      tasks: [],
      filtered: [],
      selectedTask: null,
      autoTimer: null,
      fallbackTimer: null,
      eventSource: null,
      streamReconnectTimer: null,
      streamLastEventId: 0,
      recentRuns: [],
      audit: [],
      stageOpen: {
        todo: true,
        ready: true,
        in_progress: true,
        review: true,
        blocked: true,
        done: false,
        dropped: false,
      },
    };

    async function api(url, opts) {
      const res = await fetch(url, opts);
      if (!res.ok) throw new Error(await res.text());
      return await res.json();
    }

    function statusClass(status) {
      return `status-${String(status || 'unknown').replaceAll('_', '-')}`;
    }

    function stageClass(stage) {
      return `stage-${String(stage || 'other')}`;
    }

    function stageOf(status) {
      if (status === 'todo') return 'todo';
      if (status === 'ready') return 'ready';
      if (status === 'in_progress') return 'in_progress';
      if (status === 'review') return 'review';
      if (status === 'done') return 'done';
      if (status === 'dropped') return 'dropped';
      if (status === 'blocked') return 'blocked';
      return 'other';
    }

    function statusOrder() {
      return ['todo', 'ready', 'in_progress', 'review', 'blocked', 'done', 'dropped'];
    }

    async function loadProjects() {
      const data = await api('/api/projects');
      state.projects = data.projects || [];
      const sel = document.getElementById('projectSelect');
      const current = sel.value;
      sel.innerHTML = state.projects.map(p => `<option value=\"${p}\">${p}</option>`).join('');
      if (!state.projects.length) {
        return;
      }
      if (current && state.projects.includes(current)) sel.value = current;
      sel.onchange = async () => {
        await refreshAll();
        restartStream();
      };
    }

    function currentProject() {
      return document.getElementById('projectSelect').value;
    }

    async function loadTasks() {
      const data = await api(`/api/tasks?project=${encodeURIComponent(currentProject())}`);
      state.tasks = data.tasks || [];
      const sources = [...new Set(state.tasks.map(t => t.source || 'unknown'))].sort();
      const sourceSel = document.getElementById('sourceFilter');
      const oldSource = sourceSel.value;
      sourceSel.innerHTML = '<option value="">all sources</option>' + sources.map(s => `<option value=\"${s}\">${s}</option>`).join('');
      if (sources.includes(oldSource)) sourceSel.value = oldSource;
      renderTaskList();
    }

    async function loadStatsAndRuns() {
      const project = currentProject();
      const runsData = await api(`/api/runs/recent?project=${encodeURIComponent(project)}&limit=20`);
      const auditData = await api(`/api/audit?project=${encodeURIComponent(project)}&limit=30`);
      state.recentRuns = runsData.runs || [];
      state.audit = auditData.events || [];
      renderRecentRuns();
      renderAudit();
    }

    function renderTaskList() {
      const q = document.getElementById('q').value.trim().toLowerCase();
      const source = document.getElementById('sourceFilter').value;
      state.filtered = state.tasks.filter(t => {
        if (source && (t.source || 'unknown') !== source) return false;
        if (q && !t.title.toLowerCase().includes(q)) return false;
        return true;
      });
      const root = document.getElementById('taskList');
      if (!state.filtered.length) {
        root.innerHTML = '<div class=\"task\"><span class=\"sub\">No tasks</span></div>';
        return;
      }
      const grouped = {};
      for (const st of statusOrder()) grouped[st] = [];
      for (const t of state.filtered) {
        const st = stageOf(t.status);
        if (!grouped[st]) grouped[st] = [];
        grouped[st].push(t);
      }
      root.innerHTML = `<div class=\"status-accordion\">${statusOrder().map(st => {
        const tasks = grouped[st] || [];
        const isOpen = state.stageOpen[st] !== undefined ? state.stageOpen[st] : tasks.length > 0;
        const tasksHtml = tasks.length
          ? tasks.map(t => `
            <div class=\"task ${state.selectedTask && state.selectedTask.id === t.id ? 'active' : ''}\" onclick=\"openTask(${t.id})\">
              <div class=\"task-title\">#${t.id} ${t.title}</div>
              <div class=\"meta\">
                <span>p${t.priority}/i${t.impact}/e${t.effort}</span>
                <span>${t.assigned_agent || '-'}</span>
              </div>
            </div>`).join('')
          : '<div class=\"task\"><span class=\"sub\">No tasks</span></div>';
        return `
          <details class=\"status-group\" ${isOpen ? 'open' : ''} ontoggle=\"onStageToggle('${st}', this.open)\">
            <summary class=\"status-summary\">
              <span class=\"status-heading\"><span class=\"badge-chip ${stageClass(st)}\">${st}</span></span>
              <span class=\"status-count\">${tasks.length}</span>
            </summary>
            <div class=\"group-body\">${tasksHtml}</div>
          </details>`;
      }).join('')}</div>`;
    }

    function onStageToggle(stage, open) {
      state.stageOpen[stage] = Boolean(open);
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
          <div class=\"meta\"><span class=\"${statusClass(r.status)}\">${r.status}</span><span>${r.adapter}</span><span>${r.agent_name}</span><span>${r.started_at}</span></div>
        </div>
      `).join('');
    }

    function renderAudit() {
      const root = document.getElementById('auditList');
      if (!state.audit.length) {
        root.innerHTML = '<div class=\"sub\">No audit events yet</div>';
        return;
      }
      root.innerHTML = state.audit.map(e => `
        <div class=\"run-item\">
          <div><strong>#${e.task_id || '-'}</strong> ${e.event_type || 'event'}</div>
          <div class=\"meta\"><span>${e.event_family || '-'}</span><span class=\"${statusClass(e.status_from || '')}\">${e.status_from || '-'}</span><span>-></span><span class=\"${statusClass(e.status_to || '')}\">${e.status_to || '-'}</span><span>${e.occurred_at || e.recorded_at || '-'}</span></div>
          <div class=\"sub\">${e.summary || '-'}</div>
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
      const links = data.links || {};
      const pr = data.pr_summary || {};
      const issueUrl = links.issue_url || '';
      const prUrl = links.pr_url || '';
      const repo = links.repo || '';
      const prCandidates = links.pr_candidates || [];
      const latestRuns = (data.runs || []).slice(0, 5);
      const historyRows = (data.history || []).slice(0, 12);
      const detail = document.getElementById('detail');
      detail.innerHTML = `
        <div class=\"detail-top\">
          <span class=\"badge\">task #${t.id}</span>
          <span class=\"badge-chip ${stageClass(stageOf(t.status))}\">${stageOf(t.status)}</span>
          <span class=\"badge-chip ${statusClass(t.status)}\">status: ${t.status}</span>
        </div>
        <div class=\"detail-title\">${t.title}</div>
        <div class=\"sub\">source: ${t.source || '-'} ${t.external_id || ''} · agent: ${t.assigned_agent || '-'} · lease: ${t.lease_until || '-'}</div>
        <div class=\"detail-grid\">
          <div class=\"stat\"><div class=\"k\">Priority / Impact / Effort</div><div class=\"v\">${t.priority} / ${t.impact} / ${t.effort}</div></div>
          <div class=\"stat\"><div class=\"k\">Runs</div><div class=\"v\">${pr.run_count || 0}</div></div>
          <div class=\"stat\"><div class=\"k\">Latest Gate</div><div class=\"v\">${pr.latest_gate_passed === null || pr.latest_gate_passed === undefined ? '-' : (pr.latest_gate_passed ? 'pass' : 'fail')}</div></div>
        </div>
        <div class=\"history\">
          <h4 style=\"margin:0 0 8px\">PR Detail</h4>
          <div class=\"timeline-item\">PR summary: ${pr.latest_result_summary || 'No execution summary yet'}</div>
          <div class=\"timeline-item\">Latest run status: ${pr.latest_run_status || '-'}</div>
          <div class=\"timeline-item\">Repo: ${repo ? `<a href=\"https://github.com/${repo}\" target=\"_blank\">${repo}</a>` : '-'}</div>
          <div class=\"timeline-item\">Issue: ${issueUrl ? `<a href=\"${issueUrl}\" target=\"_blank\">${issueUrl}</a>` : '-'}</div>
          <div class=\"timeline-item\">Primary PR: ${prUrl ? `<a href=\"${prUrl}\" target=\"_blank\">${prUrl}</a>` : '-'}</div>
          <div class=\"timeline-item\">Related PR Links: ${prCandidates.length ? prCandidates.map(u => `<a href=\"${u}\" target=\"_blank\">${u}</a>`).join('<br/>') : '-'}</div>
        </div>
        <div class=\"detail-actions\">
          <select id=\"adapterSel\"><option value=\"mock\">mock</option></select>
          <input id=\"agentInput\" placeholder=\"agent name\" value=\"web-console-agent\" />
          <button onclick=\"runTask(${t.id})\">Run Task</button>
        </div>
        <div class=\"detail-actions\">
          <select id=\"moveStatusSel\">
            <option value=\"todo\">todo</option>
            <option value=\"ready\">ready</option>
            <option value=\"in_progress\">in_progress</option>
            <option value=\"review\">review</option>
            <option value=\"done\">done</option>
            <option value=\"dropped\">dropped</option>
            <option value=\"blocked\">blocked</option>
          </select>
          <input id=\"moveNoteInput\" placeholder=\"note for manual transition\" />
          <label class=\"sub\" style=\"display:flex;align-items:center;gap:4px;\"><input id=\"moveForceCk\" type=\"checkbox\" style=\"width:auto;\" />force</label>
          <button class=\"secondary\" onclick=\"moveTask(${t.id}, null, null, null)\">Update Flow</button>
        </div>
        <div class=\"history\">
          <h4 style=\"margin:0 0 8px\">Flow History</h4>
          ${historyRows.map(h => `<div class=\"timeline-item\">${h.changed_at}: ${h.from_status || '-'} -> ${h.to_status} ${h.note ? `| ${h.note}` : ''}</div>`).join('') || '<div class=\"sub\">No history</div>'}
        </div>
        <div class=\"history\">
          <h4 style=\"margin:0 0 8px\">Recent Runs (Top 5)</h4>
          ${latestRuns.map(r => `
            <div class=\"timeline-item\">
              <span class=\"${r.status === 'failed' ? 'err' : 'ok'}\">run #${r.id} ${r.status}</span>
              <div class=\"sub\">${r.trigger_type} | ${r.adapter} | ${r.agent_name} | gate=${r.gate_passed ? 'pass' : 'fail'}</div>
              <div class=\"sub\">${(r.steps || []).map(s => `${s.step_name}:${s.status}`).join(' | ') || 'no steps'}</div>
            </div>
          `).join('') || '<div class=\"sub\">No runs yet</div>'}
        </div>
      `;
      const moveSel = document.getElementById('moveStatusSel');
      if (moveSel) moveSel.value = t.status;
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

    async function moveTask(taskId, forcedStatus, forcedNote, forcedForce) {
      const toStatus = forcedStatus || document.getElementById('moveStatusSel').value;
      const note = forcedNote !== null && forcedNote !== undefined ? forcedNote : (document.getElementById('moveNoteInput').value || '');
      const force = forcedForce !== null && forcedForce !== undefined ? Boolean(forcedForce) : Boolean(document.getElementById('moveForceCk')?.checked);
      try {
        const res = await api(`/api/task/${taskId}/move`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ to_status: toStatus, note, force })
        });
        await refreshAll();
        await openTask(taskId);
        alert(res.message || 'task moved');
      } catch (err) {
        alert(`move failed: ${err}`);
      }
    }

    async function refreshAll() {
      if (!currentProject()) {
        await loadProjects();
      }
      if (!currentProject()) {
        document.getElementById('taskList').innerHTML = '<div class=\"task\"><span class=\"sub\">No projects yet. Create one via CLI first.</span></div>';
        document.getElementById('recentRuns').innerHTML = '<div class=\"item sub\">No project selected.</div>';
        document.getElementById('auditList').innerHTML = '<div class=\"item sub\">No project selected.</div>';
        return;
      }
      await loadTasks();
      await loadStatsAndRuns();
      if (state.selectedTask) {
        const exists = state.tasks.find(t => t.id === state.selectedTask.id);
        if (exists) await openTask(state.selectedTask.id);
      }
    }

    function setConnState(text) {
      const el = document.getElementById('connState');
      if (el) el.textContent = text;
    }

    function stopFallbackPolling() {
      if (state.fallbackTimer) {
        clearInterval(state.fallbackTimer);
        state.fallbackTimer = null;
      }
    }

    function startFallbackPolling() {
      if (state.fallbackTimer) return;
      state.fallbackTimer = setInterval(() => {
        refreshAll().catch(err => console.error(err));
      }, 15000);
    }

    function closeStream() {
      if (state.eventSource) {
        state.eventSource.close();
        state.eventSource = null;
      }
      if (state.streamReconnectTimer) {
        clearTimeout(state.streamReconnectTimer);
        state.streamReconnectTimer = null;
      }
    }

    async function onStreamEvent(raw) {
      let evt = null;
      try {
        evt = JSON.parse(raw.data || '{}');
      } catch (_err) {
        return;
      }
      if (evt && Number.isFinite(Number(evt.id))) {
        state.streamLastEventId = Math.max(state.streamLastEventId, Number(evt.id));
      }
      await refreshAll();
    }

    function restartStream() {
      closeStream();
      const project = currentProject();
      if (!project) return;
      const url = `/api/events?project=${encodeURIComponent(project)}&last_event_id=${state.streamLastEventId || 0}`;
      const es = new EventSource(url);
      state.eventSource = es;

      es.onopen = () => {
        stopFallbackPolling();
        setConnState('Stream: LIVE');
      };
      es.onmessage = (ev) => {
        onStreamEvent(ev).catch(err => console.error(err));
      };
      es.onerror = () => {
        setConnState('Stream: RETRY');
        startFallbackPolling();
        if (state.streamReconnectTimer) return;
        state.streamReconnectTimer = setTimeout(() => {
          state.streamReconnectTimer = null;
          restartStream();
        }, 3000);
      };
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
      let lastErr = null;
      for (let attempt = 0; attempt < 3; attempt++) {
        try {
          await loadProjects();
          await refreshAll();
          restartStream();
          return;
        } catch (err) {
          lastErr = err;
          const delay = 1000 * Math.pow(2, attempt);
          await new Promise((resolve) => setTimeout(resolve, delay));
        }
      }
      throw lastErr || new Error('boot failed');
    }

    window.addEventListener('beforeunload', () => {
      closeStream();
      stopFallbackPolling();
    });

    boot().catch(err => {
      document.body.innerHTML = `
        <div style=\"padding:24px\">
          <h3 style=\"margin:0 0 10px\">Console load failed</h3>
          <pre class=\"err\" style=\"white-space:pre-wrap\">${String(err)}</pre>
          <button class=\"secondary\" onclick=\"window.location.reload()\">Retry</button>
        </div>
      `;
    });
  </script>
</body>
</html>
"""

WEB_ROOT = Path(__file__).resolve().parent / "web"
CONSOLE_TEMPLATE_PATH = WEB_ROOT / "templates" / "console.html"
CONSOLE_CSS_PATH = WEB_ROOT / "static" / "console.css"
CONSOLE_JS_PATH = WEB_ROOT / "static" / "console.js"


def _read_text_or_fallback(path: Path, fallback: str) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return fallback


def _load_console_html(asset_version: str) -> str:
    html = _read_text_or_fallback(CONSOLE_TEMPLATE_PATH, INDEX_HTML)
    return html.replace("{{ASSET_VERSION}}", asset_version)


# Keep this symbol for tests/backward-compatibility, now sourced from template files.
INDEX_HTML = _load_console_html("dev")
CONSOLE_CSS = _read_text_or_fallback(CONSOLE_CSS_PATH, "")
CONSOLE_JS = _read_text_or_fallback(CONSOLE_JS_PATH, "")


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


def _flow_stage_for_status(status: str) -> str:
    mapping = {
        "todo": "todo",
        "ready": "ready",
        "in_progress": "in_progress",
        "review": "review",
        "done": "done",
        "dropped": "dropped",
        "blocked": "blocked",
    }
    return mapping.get(status, "other")


def _extract_pr_links(runs: list[dict[str, Any]]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    pat = re.compile(r"https://github\.com/[^\s]+/pull/\d+")
    for run in runs:
        texts: list[str] = []
        result_summary = run.get("result_summary")
        if isinstance(result_summary, str):
            texts.append(result_summary)
        for step in run.get("steps", []):
            excerpt = step.get("log_excerpt")
            if isinstance(excerpt, str):
                texts.append(excerpt)
        for text in texts:
            for match in pat.findall(text):
                if match not in seen:
                    seen.add(match)
                    out.append(match)
    return out


def _build_task_links(task: dict[str, Any], repo_full_name: str | None, runs: list[dict[str, Any]]) -> dict[str, Any]:
    source = str(task.get("source") or "")
    external_id = str(task.get("external_id") or "")
    task_pr = str(task.get("pr_url") or "").strip() or None
    issue_url = None
    if source == "github" and repo_full_name and external_id:
        issue_url = f"https://github.com/{repo_full_name}/issues/{external_id}"
    run_prs = _extract_pr_links(runs)
    pr_url = task_pr or (run_prs[0] if run_prs else None)
    return {
        "repo": repo_full_name,
        "issue_url": issue_url,
        "pr_url": pr_url,
        "pr_candidates": run_prs,
    }


class EventStreamBroker:
    def __init__(self, store: Store, *, max_events: int = 400) -> None:
        self._store = store
        self._max_events = max(50, max_events)
        self._cond = threading.Condition()
        self._events: list[dict[str, Any]] = []

    def publish(self, project: str, event_item: dict[str, Any]) -> int:
        if "id" not in event_item:
            raise ValueError("event_item must include id")
        item = dict(event_item)
        item["project"] = project
        with self._cond:
            self._events.append(item)
            if len(self._events) > self._max_events:
                self._events = self._events[-self._max_events :]
            self._cond.notify_all()
            return int(item["id"])

    def since(self, project: str, last_event_id: int) -> list[dict[str, Any]]:
        rows = self._store.list_project_events(project, after_id=last_event_id, limit=self._max_events)
        if rows:
            return rows
        with self._cond:
            return [e for e in self._events if e["project"] == project and int(e["id"]) > last_event_id]

    def wait_for(self, project: str, last_event_id: int, timeout_sec: float = 15.0) -> list[dict[str, Any]]:
        deadline = time.time() + max(0.1, timeout_sec)
        while True:
            try:
                rows = self._store.list_project_events(project, after_id=last_event_id, limit=self._max_events)
            except sqlite3.Error:
                return []
            if rows:
                return rows
            remaining = deadline - time.time()
            if remaining <= 0:
                return []
            with self._cond:
                self._cond.wait(timeout=min(remaining, 1.0))


def _latest_running_run_id(store: Store, task_id: int) -> int | None:
    for run in store.list_runs(task_id):
        if str(run["status"]) == "running":
            return int(run["id"])
    return None


def _record_task_progress(
    store: Store,
    *,
    task_id: int,
    agent: str,
    step: str,
    detail: str,
    status: str,
    lease_minutes: int,
) -> dict[str, Any]:
    run_id = _latest_running_run_id(store, task_id)
    if run_id is None:
        return {"ok": False, "error": "no running run for task"}
    task = store.get_task(task_id)
    if task is None:
        return {"ok": False, "error": "task not found"}
    heartbeat_ok = store.heartbeat(
        task_id,
        agent,
        lease_minutes=lease_minutes,
        ledger_event={
            "run_id": run_id,
            "event_family": "feedback",
            "event_type": "progress.reported",
            "actor_type": "agent",
            "actor_id": agent,
            "source_type": "manual",
            "source_ref": f"console:task:{task_id}:progress",
            "run_status_from": "running",
            "run_status_to": "running",
            "severity": "info",
            "summary": f"{agent} reported progress on {step}",
            "evidence": {
                "step": step,
                "detail": detail,
                "status": status,
            },
            "context": {"lease_minutes": lease_minutes},
        },
    )
    if not heartbeat_ok:
        return {"ok": False, "error": "heartbeat ignored (not owner or not in_progress)"}
    step_id = store.append_run_step(run_id, step, status, detail or None)
    return {"ok": True, "run_id": run_id, "step_id": step_id, "heartbeat_ok": heartbeat_ok}


def _create_task_from_payload(store: Store, payload: dict[str, Any]) -> dict[str, Any]:
    project = str(payload.get("project") or "").strip()
    title = str(payload.get("title") or "").strip()
    if not project or not title:
        return {"ok": False, "error": "project and title are required"}
    try:
        priority = int(payload.get("priority", 3))
        impact = int(payload.get("impact", 3))
        effort = int(payload.get("effort", 3))
    except (TypeError, ValueError):
        return {"ok": False, "error": "priority, impact, effort must be integers"}
    try:
        task_id = store.add_task(
            project=project,
            title=title,
            description=str(payload.get("description")) if payload.get("description") is not None else None,
            priority=priority,
            impact=impact,
            effort=effort,
            source=str(payload.get("source")) if payload.get("source") is not None else None,
            external_id=str(payload.get("external_id")) if payload.get("external_id") is not None else None,
        )
    except ValueError as exc:
        return {"ok": False, "error": str(exc)}
    task = store.get_task(task_id)
    return {"ok": True, "task_id": task_id, "task": _task_to_dict(task) if task is not None else None}


def _validate_manual_transition(from_status: str, to_status: str) -> str | None:
    allowed = {
        "todo": {"ready", "blocked", "dropped"},
        "ready": {"todo", "in_progress", "review", "blocked", "dropped"},
        "in_progress": {"ready", "review", "blocked"},
        "review": {"ready", "done", "blocked"},
        "blocked": {"todo", "ready", "in_progress", "dropped"},
        "done": set(),
        "dropped": set(),
    }
    next_set = allowed.get(from_status)
    if next_set is None:
        return f"unknown current status: {from_status}"
    if to_status not in next_set:
        return f"transition not allowed: {from_status} -> {to_status}"
    return None


def _build_handler(
    store: Store,
    runner: Runner,
    discovery: IssueDiscoveryService,
    webhook: GithubCommentWebhookService,
    github_webhook_secret: str | None,
    *,
    reload_assets: bool = False,
):
    broker = EventStreamBroker(store)
    asset_version = str(int(time.time()))
    html_cache = _load_console_html(asset_version)
    css_cache = _read_text_or_fallback(CONSOLE_CSS_PATH, CONSOLE_CSS)
    js_cache = _read_text_or_fallback(CONSOLE_JS_PATH, CONSOLE_JS)

    def _current_html() -> str:
        return _load_console_html(str(int(time.time()))) if reload_assets else html_cache

    def _current_css() -> str:
        return _read_text_or_fallback(CONSOLE_CSS_PATH, css_cache) if reload_assets else css_cache

    def _current_js() -> str:
        return _read_text_or_fallback(CONSOLE_JS_PATH, js_cache) if reload_assets else js_cache

    def _on_async_run_finished(project: str, task_id: int, run: Any) -> None:
        timeline = store.list_task_timeline(task_id, limit=1)
        if timeline:
            broker.publish(project, timeline[0])

    def _publish_latest_task_event(task_id: int) -> None:
        task = store.get_task(task_id)
        if task is None:
            return
        timeline = store.list_task_timeline(task_id, limit=1)
        if timeline:
            broker.publish(task.project, timeline[0])

    def _publish_latest_run_event(run_id: int) -> None:
        timeline = store.list_run_timeline(run_id, limit=1)
        if timeline:
            broker.publish(str(timeline[0]["project"]), timeline[0])

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
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def _send_text(self, text: str, content_type: str) -> None:
            data = text.encode("utf-8")
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", content_type)
            self.send_header("Cache-Control", "no-store")
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
                self._send_html(_current_html())
                return

            if path == "/static/console.css":
                self._send_text(_current_css(), "text/css; charset=utf-8")
                return

            if path == "/static/console.js":
                self._send_text(_current_js(), "application/javascript; charset=utf-8")
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

            if path == "/api/flow":
                project = query.get("project", [None])[0]
                if not project:
                    self._send_json({"error": "project is required"}, status=HTTPStatus.BAD_REQUEST)
                    return
                tasks = [_task_to_dict(t) for t in store.list_tasks(project)]
                grouped: dict[str, list[dict[str, Any]]] = {}
                for task in tasks:
                    stage = _flow_stage_for_status(str(task.get("status", "")))
                    grouped.setdefault(stage, []).append(task)
                self._send_json({"project": project, "stages": grouped})
                return

            if path == "/api/events":
                project = query.get("project", [None])[0]
                if not project:
                    self._send_json({"error": "project is required"}, status=HTTPStatus.BAD_REQUEST)
                    return
                raw_last = query.get("last_event_id", [self.headers.get("Last-Event-ID", "0")])[0]
                try:
                    last_event_id = max(0, int(str(raw_last)))
                except ValueError:
                    last_event_id = 0

                self.send_response(HTTPStatus.OK)
                self.send_header("Content-Type", "text/event-stream; charset=utf-8")
                self.send_header("Cache-Control", "no-cache")
                self.send_header("Connection", "keep-alive")
                self.end_headers()

                def emit(event_item: dict[str, Any]) -> None:
                    self.wfile.write(f"id: {int(event_item['id'])}\n".encode("utf-8"))
                    self.wfile.write(f"event: {event_item['event_type']}\n".encode("utf-8"))
                    self.wfile.write(f"data: {json.dumps(event_item)}\n\n".encode("utf-8"))

                try:
                    backlog = broker.since(project, last_event_id)
                    for event_item in backlog:
                        emit(event_item)
                        last_event_id = int(event_item["id"])
                    self.wfile.flush()

                    while True:
                        events = broker.wait_for(project, last_event_id, timeout_sec=15.0)
                        if not events:
                            self.wfile.write(b": keep-alive\n\n")
                            self.wfile.flush()
                            continue
                        for event_item in events:
                            emit(event_item)
                            last_event_id = int(event_item["id"])
                        self.wfile.flush()
                except (BrokenPipeError, ConnectionResetError):
                    return

            if path == "/api/audit":
                project = query.get("project", [None])[0]
                if not project:
                    self._send_json({"error": "project is required"}, status=HTTPStatus.BAD_REQUEST)
                    return
                raw_limit = query.get("limit", ["50"])[0]
                try:
                    limit = max(1, min(200, int(raw_limit)))
                except ValueError:
                    limit = 50
                rows = store.list_project_audit_events(project, limit=limit)
                self._send_json({"project": project, "events": rows})
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
                    recent_runs = [_row_to_dict(r) for r in store.list_runs(task_id)]
                    for run in recent_runs:
                        run["steps"] = [_row_to_dict(s) for s in store.list_run_steps(int(run["id"]))]
                    timeline = store.list_task_timeline(task_id, limit=50)
                    history = [_row_to_dict(h) for h in store.list_status_history(task_id)]
                    task_dict = _task_to_dict(task)
                    repo = store.get_project_repo(task.project)
                    latest_run = recent_runs[0] if recent_runs else None
                    links = _build_task_links(task_dict, repo, recent_runs)
                    pr_summary = {
                        "latest_run_status": latest_run["status"] if latest_run else None,
                        "latest_gate_passed": bool(latest_run["gate_passed"]) if latest_run else None,
                        "latest_result_summary": latest_run["result_summary"] if latest_run else None,
                        "run_count": len(recent_runs),
                    }
                    self._send_json(
                        {
                            "task": task_dict,
                            "runs": recent_runs,
                            "recent_runs": recent_runs,
                            "timeline": timeline,
                            "history": history,
                            "links": links,
                            "pr_summary": pr_summary,
                            "derived_summary": derive_task_summary(timeline),
                        }
                    )
                    return

            self._send_json({"error": "not found"}, status=HTTPStatus.NOT_FOUND)

        def do_POST(self) -> None:  # noqa: N802
            parsed = urlparse(self.path)
            path = parsed.path
            query = parse_qs(parsed.query)
            body = self._read_body()

            if path == "/api/tasks":
                payload = self._parse_json(body)
                out = _create_task_from_payload(store, payload)
                if not out.get("ok"):
                    self._send_json({"ok": False, "error": out.get("error")}, status=HTTPStatus.BAD_REQUEST)
                    return
                self._send_json({"ok": True, "task_id": out["task_id"], "task": out.get("task")})
                return

            if path.startswith("/api/task/") and path.endswith("/progress"):
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
                agent = str(payload.get("agent") or task.assigned_agent or "").strip()
                if not agent:
                    self._send_json({"error": "agent is required"}, status=HTTPStatus.BAD_REQUEST)
                    return
                step = str(payload.get("step") or "progress").strip() or "progress"
                detail = str(payload.get("detail") or "").strip()
                step_status = str(payload.get("status") or "in_progress").strip() or "in_progress"
                raw_lease = payload.get("lease_minutes", 30)
                try:
                    lease_minutes = max(1, min(240, int(raw_lease)))
                except (TypeError, ValueError):
                    lease_minutes = 30
                out = _record_task_progress(
                    store,
                    task_id=task_id,
                    agent=agent,
                    step=step,
                    detail=detail,
                    status=step_status,
                    lease_minutes=lease_minutes,
                )
                if not out.get("ok"):
                    self._send_json({"ok": False, "error": out.get("error")}, status=HTTPStatus.CONFLICT)
                    return
                _publish_latest_run_event(int(out["run_id"]))
                self._send_json(
                    {
                        "ok": True,
                        "task_id": task_id,
                        "run_id": out["run_id"],
                        "step_id": out["step_id"],
                        "heartbeat_ok": out["heartbeat_ok"],
                    }
                )
                return

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
                if run.task is not None:
                    _publish_latest_task_event(run.task.id)
                return

            if path.startswith("/api/task/") and path.endswith("/move"):
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
                to_status = str(payload.get("to_status") or "").strip()
                note = payload.get("note")
                force = bool(payload.get("force", False))
                if not to_status:
                    self._send_json({"error": "to_status is required"}, status=HTTPStatus.BAD_REQUEST)
                    return
                task = store.get_task(task_id)
                if task is None:
                    self._send_json({"error": "task not found"}, status=HTTPStatus.NOT_FOUND)
                    return

                if not force:
                    transition_error = _validate_manual_transition(task.status, to_status)
                    if transition_error is not None:
                        self._send_json({"error": transition_error}, status=HTTPStatus.BAD_REQUEST)
                        return

                    if to_status in {"review", "done"}:
                        runs = store.list_runs(task_id)
                        latest = runs[0] if runs else None
                        latest_passed = bool(latest and latest["status"] == "passed" and bool(latest["gate_passed"]))
                        if not latest_passed:
                            self._send_json(
                                {"error": "gate check required: latest run must be passed with gate_passed=1 (or use force=true)"},
                                status=HTTPStatus.BAD_REQUEST,
                            )
                            return

                final_note = str(note) if note is not None else ""
                final_note = f"[manual-web] {final_note}".strip()
                try:
                    store.move_task(
                        task_id,
                        to_status,
                        final_note,
                        force=force,
                        ledger_event={
                            "event_family": "governance",
                            "event_type": "task.force_moved",
                            "actor_type": "user",
                            "actor_id": "web-console",
                            "source_type": "manual",
                            "source_ref": f"console:task:{task_id}:move",
                            "severity": "warning",
                            "summary": f"Manual force move to {to_status}: {final_note}",
                            "evidence": {"force": True, "note": final_note},
                            "context": {"stage": _flow_stage_for_status(to_status)},
                        }
                        if force
                        else None,
                    )
                except ValueError as exc:
                    self._send_json({"error": str(exc)}, status=HTTPStatus.BAD_REQUEST)
                    return
                task = store.get_task(task_id)
                self._send_json(
                    {
                        "ok": True,
                        "message": f"task {task_id} moved to {to_status}",
                        "task": _task_to_dict(task) if task is not None else None,
                        "stage": _flow_stage_for_status(to_status),
                    }
                )
                if task is not None:
                    _publish_latest_task_event(task.id)
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

                adapter = query.get("adapter", ["openclaw"])[0]
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
                    result = webhook.handle_pr_comment(
                        project=project,
                        payload=payload,
                        adapter=adapter,
                        agent_name=agent,
                        async_run=True,
                        on_run_finished=_on_async_run_finished,
                    )
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
                    result = webhook.handle_pr_comment(
                        project=project,
                        payload=payload,
                        adapter=adapter,
                        agent_name=agent,
                        async_run=True,
                        on_run_finished=_on_async_run_finished,
                    )
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
    reload: bool = False,
) -> None:
    store = Store(db_path)
    registry = AdapterRegistry()
    runner = Runner(store, registry)
    discovery = IssueDiscoveryService(store)
    webhook = GithubCommentWebhookService(store, runner)
    handler = _build_handler(
        store,
        runner,
        discovery,
        webhook,
        github_webhook_secret,
        reload_assets=reload,
    )
    server = ThreadingHTTPServer((host, port), handler)
    print(f"AgentFlow console running on http://{host}:{port}")
    print(f"Using db: {db_path}")
    print(f"GitHub webhook secret: {'enabled' if github_webhook_secret else 'disabled'}")
    print(f"Template reload: {'enabled' if reload else 'disabled'}")
    if host not in {"127.0.0.1", "localhost"}:
        print("WARNING: non-localhost bind detected; gate commands are project-controlled shell commands.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
